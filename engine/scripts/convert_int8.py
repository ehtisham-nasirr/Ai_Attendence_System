"""Post-training INT8 quantisation of an ONNX model to OpenVINO IR with NNCF (standards/17 §5).

A converted model MUST pass scripts/evaluate.py on the reference set (TAR not lower beyond the agreed
tolerance, FAR not higher) before it is used. Calibration images must be consented data kept outside Git.

    uv sync --group tools
    uv run python scripts/convert_int8.py models/face_recognition_sface_2021dec.onnx \
        --calibration /data/calibration/aligned --kind embedder --out models/sface_int8.xml
"""

import argparse
from pathlib import Path

import cv2
import numpy as np


def _load_calibration(folder: Path, kind: str, limit: int) -> list[np.ndarray]:
    tensors = []
    for path in sorted(folder.glob("*.*"))[:limit]:
        image = cv2.imread(str(path))
        if image is None:
            continue
        if kind == "embedder":
            rgb = cv2.cvtColor(cv2.resize(image, (112, 112)), cv2.COLOR_BGR2RGB)
            tensors.append(rgb.transpose(2, 0, 1)[None].astype(np.float32))
        else:
            tensors.append(cv2.resize(image, (640, 640)).transpose(2, 0, 1)[None].astype(np.float32))
    if not tensors:
        raise SystemExit(f"no calibration images found in {folder}")
    return tensors


def main() -> None:
    import nncf
    import openvino as ov

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("model", type=Path)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--kind", choices=["embedder", "detector"], required=True)
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    model = ov.Core().read_model(str(args.model))
    dataset = nncf.Dataset(_load_calibration(args.calibration, args.kind, args.samples))
    quantized = nncf.quantize(model, dataset, subset_size=min(args.samples, 300))
    ov.save_model(quantized, str(args.out))
    print(f"wrote {args.out} — run scripts/evaluate.py before using it")


if __name__ == "__main__":
    main()
