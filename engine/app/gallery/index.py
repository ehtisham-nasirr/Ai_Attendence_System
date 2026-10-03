"""In-memory FAISS gallery (requirements §9 "Matching method", NFR-5).

Cosine similarity on L2-normalised vectors via an inner-product index. Each employee has 3-10
vectors; results are aggregated to the best score per employee.
"""

from dataclasses import dataclass

import faiss
import numpy as np
import numpy.typing as npt

# Enough neighbours to always see at least two distinct employees when each has <= 10 vectors.
_SEARCH_K = 32


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    employee_code: str
    score: float


@dataclass(frozen=True)
class GallerySnapshot:
    """What the engine loads from the database: one row per enrolled vector."""

    model_name: str
    version: int
    employee_codes: list[str]
    vectors: npt.NDArray[np.float32]  # (n, dim), L2-normalised

    @property
    def employee_count(self) -> int:
        return len(set(self.employee_codes))


class GalleryIndex:
    def __init__(self, snapshot: GallerySnapshot) -> None:
        vectors = np.ascontiguousarray(snapshot.vectors, dtype=np.float32)
        if vectors.ndim != 2 or len(vectors) != len(snapshot.employee_codes):
            raise ValueError("gallery vectors and employee codes do not line up")
        self.model_name = snapshot.model_name
        self.version = snapshot.version
        self.dim = vectors.shape[1] if len(vectors) else 0
        self._codes = np.array(snapshot.employee_codes, dtype=object)
        self._index: faiss.IndexFlatIP | None = None
        if len(vectors):
            self._index = faiss.IndexFlatIP(self.dim)
            self._index.add(vectors)

    @property
    def size(self) -> int:
        return 0 if self._index is None else int(self._index.ntotal)

    def search(
        self, embeddings: npt.NDArray[np.float32], top_employees: int = 3
    ) -> list[list[MatchCandidate]]:
        """Best score per employee for each query, highest first (at most `top_employees` each)."""
        if self._index is None or len(embeddings) == 0:
            return [[] for _ in range(len(embeddings))]
        if embeddings.shape[1] != self.dim:
            raise ValueError("query dimension does not match the gallery model")
        k = min(_SEARCH_K, self.size)
        scores, ids = self._index.search(np.ascontiguousarray(embeddings, dtype=np.float32), k)
        results = []
        for row_scores, row_ids in zip(scores, ids, strict=True):
            best: dict[str, float] = {}
            for score, vector_id in zip(row_scores, row_ids, strict=True):
                if vector_id < 0:
                    continue
                code = str(self._codes[vector_id])
                if score > best.get(code, -2.0):
                    best[code] = float(score)
            ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)[:top_employees]
            results.append([MatchCandidate(code, score) for code, score in ranked])
        return results
