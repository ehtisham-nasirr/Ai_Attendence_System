"""Best-crop selection (requirements §10.1 steps 6-7)."""

import numpy as np
from conftest import make_crop, matches

from app.pipeline.best_crops import BestCrops


def test_keeps_best_three_by_quality() -> None:
    crops = BestCrops(3)
    for crop_id, quality in enumerate([0.5, 0.6, 0.7, 0.9, 0.4], start=1):
        crops.offer(make_crop(crop_id, quality))
    assert [c.quality for c in crops.crops] == [0.9, 0.7, 0.6]


def test_embedded_crops_are_never_evicted() -> None:
    crops = BestCrops(3)
    for crop_id in (1, 2, 3):
        crops.offer(make_crop(crop_id, 0.5))
    for crop_id in (1, 2, 3):
        crops.record_embedding(crop_id, np.zeros(4, dtype=np.float32), matches(("A", 0.5)))
    assert not crops.offer(make_crop(4, 0.99))
    assert len(crops.embedded) == 3


def test_unembedded_crop_is_replaced_by_a_better_one() -> None:
    crops = BestCrops(2)
    crops.offer(make_crop(1, 0.5))
    crops.offer(make_crop(2, 0.6))
    crops.record_embedding(2, np.zeros(4, dtype=np.float32), [])
    assert crops.offer(make_crop(3, 0.7))
    assert {c.crop_id for c in crops.crops} == {2, 3}
    assert not crops.offer(make_crop(4, 0.65))
