"""Downloads the sanctioned model files and verifies their SHA-256 (standards/17 §5).

Model files are never committed to Git. Only permissively licensed models are downloaded:

- YuNet 2023mar (detector, OpenCV Zoo, MIT)
- SFace 2021dec (embedder, OpenCV Zoo, Apache-2.0)

Not downloaded on purpose:
- ArcFace R50 (`buffalo_l/w600k_r50.onnx`): InsightFace weights are for non-commercial research use;
  production needs a commercial licence first (requirements §9). Place the licensed file manually and
  set ENGINE_EMBEDDER=arcface_r50 / ENGINE_EMBEDDER_MODEL_PATH.
- MiniFASNet (liveness): no official ONNX release exists. Convert the official Silent-Face-Anti-Spoofing
  weights (Apache-2.0, github.com/minivision-ai/Silent-Face-Anti-Spoofing) to ONNX, record its SHA-256
  in this file, and set ENGINE_LIVENESS_MODEL_PATH (docs/open-questions.md Q4).

    uv run python scripts/download_models.py --dest models
"""

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

# Official OpenCV Zoo files, mirrored by the OpenCV organisation on Hugging Face.
MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    failures = 0
    for name, (url, expected) in MODELS.items():
        target = dest / name
        if target.is_file() and sha256(target) == expected:
            print(f"ok       {name} (already present)")
            continue
        temp = target.with_suffix(".part")
        urllib.request.urlretrieve(url, temp)  # noqa: S310  # fixed https URLs above
        actual = sha256(temp)
        if actual != expected:
            temp.unlink()
            print(f"MISMATCH {name}: expected {expected}, got {actual}", file=sys.stderr)
            failures += 1
            continue
        temp.replace(target)
        print(f"ok       {name}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dest", type=Path, default=Path("models"))
    args = parser.parse_args()
    sys.exit(1 if download(args.dest) else 0)


if __name__ == "__main__":
    main()
