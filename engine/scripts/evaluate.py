"""Accuracy evaluation: TAR / FAR at the configured threshold and margin, plus an ROC sweep (§16 Phase 1).

Input folder (consented test data only, stored outside Git — standards/12, standards/18):

    <root>/gallery/<employee_code>/*.jpg     enrollment photos (3-10 per person)
    <root>/probes/<employee_code>/*.jpg      passes of enrolled people
    <root>/probes/_unknown/*.jpg             passes of people who are not enrolled

A probe is a single face crop/photo here; the track-level 2-of-3 vote in the live pipeline is stricter.

    uv run python scripts/evaluate.py /data/eval --threshold 0.36 --margin 0.08 --out eval.json
"""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

UNKNOWN = "_unknown"


@dataclass
class ProbeScore:
    true_code: str  # UNKNOWN for people not in the gallery
    best_code: str | None
    best: float
    second: float


@dataclass
class Metrics:
    threshold: float
    margin: float
    genuine_probes: int
    impostor_probes: int
    tar: float  # genuine probes accepted as the right person
    far: float  # probes accepted as the WRONG person (incl. unknowns accepted as anyone)
    frr: float


def compute_metrics(scores: list[ProbeScore], threshold: float, margin: float) -> Metrics:
    genuine = [s for s in scores if s.true_code != UNKNOWN]
    accepted = [s for s in scores if s.best >= threshold and s.best - s.second >= margin]
    correct = sum(1 for s in accepted if s.best_code == s.true_code)
    wrong = sum(1 for s in accepted if s.best_code != s.true_code)
    total = max(len(scores), 1)
    return Metrics(
        threshold=threshold,
        margin=margin,
        genuine_probes=len(genuine),
        impostor_probes=len(scores) - len(genuine),
        tar=correct / max(len(genuine), 1),
        far=wrong / total,
        frr=1 - correct / max(len(genuine), 1),
    )


def roc(scores: list[ProbeScore], margin: float) -> list[dict[str, float]]:
    return [
        {"threshold": round(t, 3), "tar": m.tar, "far": m.far}
        for t in np.arange(0.20, 0.80, 0.02)
        for m in [compute_metrics(scores, float(t), margin)]
    ]


def _embed_folder(folder: Path, detector, embedder) -> list[np.ndarray]:  # type: ignore[no-untyped-def]
    from app.models.alignment import align_face

    vectors = []
    for path in sorted(folder.glob("*.jp*g")) + sorted(folder.glob("*.png")):
        image = cv2.imread(str(path))
        if image is None:
            continue
        faces = detector.detect(image, 0.6)
        if len(faces) != 1:
            continue
        vectors.append(embedder.embed([align_face(image, faces[0].landmarks)])[0])
    return vectors


def main() -> None:
    from app.config import EngineSettings
    from app.gallery.index import GalleryIndex, GallerySnapshot
    from app.models.factory import build_detector, build_embedder

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--margin", type=float, required=True)
    parser.add_argument("--out", type=Path, default=Path("evaluation.json"))
    args = parser.parse_args()

    settings = EngineSettings()  # model choice/runtime from ENGINE_* variables
    detector, embedder = build_detector(settings, 4), build_embedder(settings, 4)
    codes, vectors = [], []
    for person in sorted((args.root / "gallery").iterdir()):
        for vector in _embed_folder(person, detector, embedder):
            codes.append(person.name)
            vectors.append(vector)
    index = GalleryIndex(GallerySnapshot(embedder.name, 1, codes, np.array(vectors, dtype=np.float32)))
    scores = []
    for person in sorted((args.root / "probes").iterdir()):
        for vector in _embed_folder(person, detector, embedder):
            [ranked] = index.search(vector[None])
            best = ranked[0] if ranked else None
            scores.append(
                ProbeScore(
                    true_code=person.name,
                    best_code=best.employee_code if best else None,
                    best=best.score if best else -1.0,
                    second=ranked[1].score if len(ranked) > 1 else -1.0,
                )
            )
    report = {
        "model": embedder.name,
        "runtime": settings.runtime,
        "gallery_employees": len(set(codes)),
        "metrics": asdict(compute_metrics(scores, args.threshold, args.margin)),
        "roc": roc(scores, args.margin),
    }
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["metrics"], indent=2))


if __name__ == "__main__":
    main()
