"""FAISS gallery tests (requirements §9 matching method, NFR-5)."""

import time

import numpy as np
import pytest

from app.gallery.index import GalleryIndex, GallerySnapshot
from app.models.base import l2_normalise


def _unit(rng: np.random.Generator, n: int, dim: int) -> np.ndarray:
    return l2_normalise(rng.standard_normal((n, dim)).astype(np.float32))


def test_best_score_per_employee_and_ranking() -> None:
    rng = np.random.default_rng(0)
    base = _unit(rng, 2, 128)
    vectors = np.vstack([base[0], base[0] * 0.9 + base[1] * 0.1, base[1]])
    snapshot = GallerySnapshot("sface", 1, ["A", "A", "B"], l2_normalise(vectors.astype(np.float32)))
    index = GalleryIndex(snapshot)
    [result] = index.search(base[:1])
    assert [m.employee_code for m in result] == ["A", "B"]
    assert result[0].score == pytest.approx(1.0, abs=1e-5)
    assert snapshot.employee_count == 2


def test_empty_gallery_returns_no_matches() -> None:
    index = GalleryIndex(GallerySnapshot("sface", 1, [], np.zeros((0, 128), dtype=np.float32)))
    assert index.search(np.ones((2, 128), dtype=np.float32)) == [[], []]


def test_dimension_mismatch_is_rejected() -> None:
    rng = np.random.default_rng(1)
    index = GalleryIndex(GallerySnapshot("sface", 1, ["A"], _unit(rng, 1, 128)))
    with pytest.raises(ValueError):
        index.search(_unit(rng, 1, 512))


def test_nfr5_5000_employees_match_under_10ms_per_face() -> None:
    """Measured on this machine, not the reference server (see batch log)."""
    rng = np.random.default_rng(2)
    codes = [f"E{i // 10:05d}" for i in range(50_000)]  # 5,000 employees x 10 photos
    index = GalleryIndex(GallerySnapshot("arcface_r50", 1, codes, _unit(rng, 50_000, 512)))
    queries = _unit(rng, 20, 512)
    index.search(queries[:1])
    started = time.perf_counter()
    for query in queries:
        index.search(query[None])
    per_face_ms = (time.perf_counter() - started) * 1000 / len(queries)
    assert per_face_ms < 10.0
