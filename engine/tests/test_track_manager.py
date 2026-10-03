"""Track lifecycle: embed best crops, vote, liveness, emit once, lock (FR-15..FR-18, NFR-2)."""

import numpy as np
from conftest import make_crop, matches

from app.pipeline.track_manager import EmbedRequest, EmitEvent, LivenessRequest, TrackManager, TrackRules
from app.pipeline.voting import VotingRules

VOTING = VotingRules(threshold=0.36, margin=0.08, min_votes=2, required_crops=3)


def _manager(liveness: bool = False) -> TrackManager:
    return TrackManager(
        TrackRules(
            voting=VOTING,
            embed_after_s=2.0,
            track_lost_s=2.0,
            liveness_required=liveness,
            liveness_spoof_threshold=0.5,
        )
    )


def _feed(manager: TrackManager, track_id: int, count: int, now: float) -> None:
    for _ in range(count):
        manager.add_crop(track_id, make_crop(manager.next_crop_id(), 0.8), now)


def _embed_all(manager: TrackManager, request: EmbedRequest, scores: list[list[tuple[str, float]]]) -> list:
    results = {
        crop.crop_id: (np.ones(128, dtype=np.float32), matches(*score))
        for crop, score in zip(request.crops, scores, strict=True)
    }
    return manager.on_embeddings(request.track_id, results)


def test_fr15_three_good_crops_trigger_one_embed_request() -> None:
    manager = _manager()
    _feed(manager, 7, 3, now=0.0)
    actions = manager.step(now=0.1)
    assert len(actions) == 1 and isinstance(actions[0], EmbedRequest)
    assert len(actions[0].crops) == 3
    assert manager.step(now=0.2) == []  # in flight: no duplicate request


def test_fr16_confirmed_track_emits_once_and_is_locked() -> None:
    manager = _manager()
    _feed(manager, 7, 3, now=0.0)
    [request] = manager.step(now=0.1)
    [event] = _embed_all(manager, request, [[("A", 0.6)], [("A", 0.5)], [("A", 0.55)]])
    assert isinstance(event, EmitEvent)
    assert event.status == "recognized" and event.employee_code == "A"
    assert event.embedding is None  # embeddings are only sent with unknown events
    assert not manager.wants_crops(7)  # locked: no more detection-to-embedding work
    assert manager.step(now=10.0) == []  # track ends silently
    assert manager.active_tracks == 0


def test_embed_after_2s_with_fewer_crops_then_waits_for_third() -> None:
    manager = _manager()
    _feed(manager, 1, 2, now=0.0)
    assert manager.step(now=1.0) == []
    manager.touch(1, now=2.0)
    [request] = manager.step(now=2.1)
    assert len(request.crops) == 2
    assert _embed_all(manager, request, [[("A", 0.6)], [("A", 0.6)]]) == []  # pending: 2 < 3
    _feed(manager, 1, 1, now=2.2)
    [second] = manager.step(now=2.3)
    assert len(second.crops) == 1
    [event] = _embed_all(manager, second, [[("A", 0.6)]])
    assert isinstance(event, EmitEvent) and event.status == "recognized"


def test_fr17_split_votes_become_unknown_at_track_end_with_embedding() -> None:
    manager = _manager()
    _feed(manager, 3, 3, now=0.0)
    [request] = manager.step(now=0.1)
    assert _embed_all(manager, request, [[("A", 0.6)], [("B", 0.6)], [("C", 0.2)]]) == []
    assert not manager.wants_crops(3)
    manager.touch(3, now=1.0)
    [event] = manager.step(now=3.5)
    assert isinstance(event, EmitEvent)
    assert event.status == "unknown" and event.employee_code is None
    assert event.embedding is not None


def test_fr17_short_track_without_embedding_gets_one_embed_then_unknown() -> None:
    manager = _manager()
    _feed(manager, 4, 1, now=0.0)
    [request] = manager.step(now=2.5)  # ended (lost > 2 s) before the embed trigger
    assert isinstance(request, EmbedRequest) and len(request.crops) == 1
    [event] = _embed_all(manager, request, [[("A", 0.9)]])
    assert isinstance(event, EmitEvent) and event.status == "unknown"  # 1 crop can never confirm


def test_track_without_usable_crops_is_dropped_silently() -> None:
    manager = _manager()
    manager.touch(9, now=0.0)
    assert manager.step(now=5.0) == []
    assert manager.active_tracks == 0


def test_fr18_liveness_pass_emits_recognized_with_score() -> None:
    manager = _manager(liveness=True)
    _feed(manager, 5, 3, now=0.0)
    [request] = manager.step(now=0.1)
    [liveness] = _embed_all(manager, request, [[("A", 0.6)]] * 3)
    assert isinstance(liveness, LivenessRequest)
    [event] = manager.on_liveness(5, real_score=0.95)
    assert event.status == "recognized" and event.liveness_score == 0.95


def test_fr18_spoof_is_never_recognized() -> None:
    manager = _manager(liveness=True)
    _feed(manager, 5, 3, now=0.0)
    [request] = manager.step(now=0.1)
    _embed_all(manager, request, [[("A", 0.6)]] * 3)
    [event] = manager.on_liveness(5, real_score=0.2)  # spoof score 0.8 > 0.5
    assert event.status == "unknown" and event.employee_code is None
    assert event.liveness_score == 0.2


def test_failed_liveness_after_retries_fails_safe_to_unknown() -> None:
    manager = _manager(liveness=True)
    _feed(manager, 5, 3, now=0.0)
    [request] = manager.step(now=0.1)
    _embed_all(manager, request, [[("A", 0.6)]] * 3)
    actions = []
    for _ in range(3):
        actions = manager.on_request_failed(5, "liveness")
    [event] = actions
    assert isinstance(event, EmitEvent) and event.status == "unknown"


def test_failed_embedding_is_retried_then_given_up() -> None:
    manager = _manager()
    _feed(manager, 6, 3, now=0.0)
    manager.step(now=0.1)
    manager.on_request_failed(6, "embed")
    assert isinstance(manager.step(now=0.2)[0], EmbedRequest)  # retried
    manager.on_request_failed(6, "embed")
    manager.step(now=0.3)
    manager.on_request_failed(6, "embed")
    assert manager.step(now=0.4) == []  # gave up: decided unknown, no more CPU spent
    assert not manager.wants_crops(6)


def test_backpressure_cancel_does_not_count_as_failure() -> None:
    manager = _manager()
    _feed(manager, 6, 3, now=0.0)
    for _ in range(5):
        [request] = manager.step(now=0.1)
        manager.cancel_in_flight(request.track_id)
    assert manager.wants_crops(6)


def test_track_table_is_bounded() -> None:
    manager = TrackManager(
        TrackRules(
            VOTING,
            embed_after_s=2.0,
            track_lost_s=2.0,
            liveness_required=False,
            liveness_spoof_threshold=0.5,
            max_tracks=4,
        )
    )
    for track_id in range(10):
        manager.touch(track_id, now=float(track_id))
    assert manager.active_tracks == 4
