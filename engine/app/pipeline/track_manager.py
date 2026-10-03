"""Per-camera track lifecycle (requirements §10.1 steps 6-11, FR-15, FR-17, FR-18).

The manager is a plain state machine: the camera worker feeds it observations and inference results,
and it returns the actions to take (embed these crops, run liveness, emit an event). It never calls
models itself, which keeps it fast and fully unit-testable.

Lifecycle of a track:
  collecting -> (3 crops embedded, vote) -> confirmed -> [liveness] -> emitted + locked
                                          -> unknown   -> emitted as Unknown when the track ends
  collecting -> track ends with < 3 embedded crops -> emitted as Unknown (FR-17, once per track)
"""

import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt

from app.gallery.index import MatchCandidate
from app.pipeline.best_crops import BestCrops, CropCandidate
from app.pipeline.voting import VoteResult, VotingRules, decide_track

logger = logging.getLogger(__name__)

# How often a failed/dropped inference request for a track is retried before giving up safely.
MAX_REQUEST_RETRIES = 2

Phase = Literal["collecting", "awaiting_liveness", "decided_unknown", "unknown_embedding", "locked"]


@dataclass(frozen=True, slots=True)
class TrackRules:
    voting: VotingRules
    embed_after_s: float
    track_lost_s: float
    liveness_required: bool
    liveness_spoof_threshold: float
    max_tracks: int = 64


@dataclass(frozen=True, slots=True)
class EmbedRequest:
    track_id: int
    crops: list[CropCandidate]


@dataclass(frozen=True, slots=True)
class LivenessRequest:
    track_id: int
    crop: CropCandidate


@dataclass(frozen=True, slots=True)
class EmitEvent:
    track_id: int
    status: Literal["recognized", "unknown"]
    employee_code: str | None
    confidence: float
    liveness_score: float | None
    crop: CropCandidate
    # Embedding of `crop`, sent (encrypted) only with unknown events for review and grouping.
    embedding: npt.NDArray[np.float32] | None


Action = EmbedRequest | LivenessRequest | EmitEvent


@dataclass
class _Track:
    track_id: int
    first_seen: float
    last_seen: float
    crops: BestCrops
    phase: Phase = "collecting"
    in_flight: set[int] = field(default_factory=set)
    decision: VoteResult | None = None
    retries: int = 0


class TrackManager:
    def __init__(self, rules: TrackRules) -> None:
        self.rules = rules
        self._tracks: dict[int, _Track] = {}
        self._next_crop_id = 1
        self.tracks_started = 0

    @property
    def active_tracks(self) -> int:
        return len(self._tracks)

    def next_crop_id(self) -> int:
        crop_id = self._next_crop_id
        self._next_crop_id += 1
        return crop_id

    def _get(self, track_id: int, now: float) -> _Track:
        track = self._tracks.get(track_id)
        if track is None:
            if len(self._tracks) >= self.rules.max_tracks:
                self._evict_oldest()
            track = _Track(track_id, now, now, BestCrops(self.rules.voting.required_crops))
            self._tracks[track_id] = track
            self.tracks_started += 1
        return track

    def _evict_oldest(self) -> None:
        oldest = min(self._tracks.values(), key=lambda t: t.last_seen)
        logger.warning("track table full; dropping oldest track", extra={"track_id": oldest.track_id})
        del self._tracks[oldest.track_id]

    def wants_crops(self, track_id: int) -> bool:
        """False for locked/decided tracks, so no detection-to-embedding work is spent on them."""
        track = self._tracks.get(track_id)
        if track is None:
            return True
        return track.phase == "collecting" and len(track.crops.embedded) < track.crops.capacity

    def touch(self, track_id: int, now: float) -> None:
        self._get(track_id, now).last_seen = now

    def add_crop(self, track_id: int, candidate: CropCandidate, now: float) -> None:
        track = self._get(track_id, now)
        track.last_seen = now
        if track.phase == "collecting":
            track.crops.offer(candidate)

    # --- periodic step ---------------------------------------------------------------------

    def step(self, now: float, embedding_allowed: bool = True) -> list[Action]:
        """Embedding triggers and track ends. Call once per processing tick."""
        actions: list[Action] = []
        for track in list(self._tracks.values()):
            ended = now - track.last_seen > self.rules.track_lost_s
            if ended:
                actions.extend(self._end(track, embedding_allowed))
            elif embedding_allowed and track.phase == "collecting":
                request = self._embedding_trigger(track, now)
                if request is not None:
                    actions.append(request)
        return actions

    def _embedding_trigger(self, track: _Track, now: float) -> EmbedRequest | None:
        if track.in_flight:
            return None
        capacity = track.crops.capacity
        if len(track.crops) < capacity and now - track.first_seen < self.rules.embed_after_s:
            return None
        pending = track.crops.unembedded[: capacity - len(track.crops.embedded)]
        if not pending:
            return None
        track.in_flight = {c.crop_id for c in pending}
        return EmbedRequest(track.track_id, pending)

    def _end(self, track: _Track, embedding_allowed: bool) -> list[Action]:
        if track.in_flight or track.phase == "awaiting_liveness":
            return []  # wait for the result (or its failure) before deciding
        if track.phase == "locked":
            del self._tracks[track.track_id]
            return []
        embedded = track.crops.embedded
        if embedded:
            del self._tracks[track.track_id]
            confidence = track.decision.confidence if track.decision else _best_score(embedded)
            return [self._unknown(track, embedded[0], confidence, liveness=None)]
        best = track.crops.best()
        if best is None:
            del self._tracks[track.track_id]  # never had a usable crop: nothing to log
            return []
        if not embedding_allowed:
            return []  # degradation step 5: embed later, never lose the track
        # One embedding of the best crop, so the Unknown entry can be reviewed and grouped (FR-17).
        track.phase = "unknown_embedding"
        track.in_flight = {best.crop_id}
        return [EmbedRequest(track.track_id, [best])]

    # --- inference results -------------------------------------------------------------------

    def on_embeddings(
        self,
        track_id: int,
        results: dict[int, tuple[npt.NDArray[np.float32], list[MatchCandidate]]],
    ) -> list[Action]:
        track = self._tracks.get(track_id)
        if track is None:
            return []
        for crop_id, (embedding, matches) in results.items():
            track.crops.record_embedding(crop_id, embedding, matches)
            track.in_flight.discard(crop_id)
        if track.in_flight:
            return []

        if track.phase == "unknown_embedding":
            del self._tracks[track_id]
            embedded = track.crops.embedded
            if not embedded:
                return []
            return [self._unknown(track, embedded[0], _best_score(embedded), liveness=None)]

        embedded = track.crops.embedded
        decision = decide_track([c.matches or [] for c in embedded], self.rules.voting)
        track.decision = decision
        if decision.outcome == "pending":
            return []
        if decision.outcome == "unknown":
            track.phase = "decided_unknown"
            return []
        if self.rules.liveness_required:
            track.phase = "awaiting_liveness"
            return [LivenessRequest(track_id, embedded[0])]
        return [self._recognized(track, decision, liveness=None)]

    def on_liveness(self, track_id: int, real_score: float) -> list[Action]:
        track = self._tracks.get(track_id)
        if track is None or track.phase != "awaiting_liveness" or track.decision is None:
            return []
        spoof_score = 1.0 - real_score
        if spoof_score > self.rules.liveness_spoof_threshold:
            # FR-18: never mark attendance from a photo/screen; keep it reviewable as Unknown (Q6).
            track.phase = "locked"
            best = track.crops.embedded[0]
            return [self._unknown(track, best, track.decision.confidence, liveness=real_score)]
        return [self._recognized(track, track.decision, liveness=real_score)]

    def on_request_failed(self, track_id: int, kind: Literal["embed", "liveness"]) -> list[Action]:
        """A request was dropped or timed out. Retry a little, then fail safe (never recognize)."""
        track = self._tracks.get(track_id)
        if track is None:
            return []
        track.retries += 1
        give_up = track.retries > MAX_REQUEST_RETRIES
        if kind == "embed":
            track.in_flight.clear()
            if track.phase == "unknown_embedding":
                track.phase = "collecting"  # _end() will retry the unknown embedding
            if give_up and track.phase == "collecting":
                track.phase = "decided_unknown"
            return []
        if give_up:
            track.phase = "locked"
            best = track.crops.embedded[0]
            confidence = track.decision.confidence if track.decision else 0.0
            return [self._unknown(track, best, confidence, liveness=None)]
        return [LivenessRequest(track_id, track.crops.embedded[0])]

    def cancel_in_flight(self, track_id: int) -> None:
        """The request never left (lane full / deferred queue full): allow it to be re-sent later.

        This is back-pressure, not a failure, so it does not count as a retry.
        """
        track = self._tracks.get(track_id)
        if track is not None:
            track.in_flight.clear()
            if track.phase == "unknown_embedding":
                track.phase = "collecting"

    # --- helpers ---------------------------------------------------------------------------

    def _recognized(self, track: _Track, decision: VoteResult, liveness: float | None) -> EmitEvent:
        track.phase = "locked"  # standards/17 §1: a confirmed track consumes no more work
        if decision.employee_code is None:
            raise ValueError("a confirmed decision must name an employee")
        return EmitEvent(
            track_id=track.track_id,
            status="recognized",
            employee_code=decision.employee_code,
            confidence=decision.confidence,
            liveness_score=liveness,
            crop=track.crops.embedded[0],
            embedding=None,
        )

    @staticmethod
    def _unknown(track: _Track, crop: CropCandidate, confidence: float, liveness: float | None) -> EmitEvent:
        return EmitEvent(
            track_id=track.track_id,
            status="unknown",
            employee_code=None,
            confidence=confidence,
            liveness_score=liveness,
            crop=crop,
            embedding=crop.embedding,
        )


def _best_score(crops: list[CropCandidate]) -> float:
    return max((c.matches[0].score for c in crops if c.matches), default=0.0)
