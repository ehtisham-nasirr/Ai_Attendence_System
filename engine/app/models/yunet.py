"""YuNet face detector (OpenCV Zoo, MIT licence) on OpenVINO / ONNX Runtime CPU.

Post-processing mirrors OpenCV's `FaceDetectorYN` (score = sqrt(cls * obj), anchor-free boxes per
stride, then NMS); `tests/test_models.py` checks it against OpenCV's own decoder.
"""

import cv2
import numpy as np
import numpy.typing as npt

from app.models.base import FaceDetection, ImageBGR
from app.models.runtime import InferenceSession

_STRIDES = (8, 16, 32)


class YuNetDetector:
    name = "yunet"

    def __init__(self, session: InferenceSession, nms_threshold: float = 0.3, top_k: int = 50) -> None:
        if len(session.input_shape) != 4 or session.input_shape[2] <= 0:
            raise ValueError("YuNet model must have a static NCHW input shape")
        self._session = session
        self._input_size = session.input_shape[2]
        self._nms_threshold = nms_threshold
        self._top_k = top_k

    @property
    def input_size(self) -> int:
        return self._input_size

    def detect(self, image: ImageBGR, score_threshold: float) -> list[FaceDetection]:
        size = self._input_size
        height, width = image.shape[:2]
        scale = min(size / width, size / height)
        resized_w, resized_h = max(1, round(width * scale)), max(1, round(height * scale))
        canvas = np.zeros((size, size, 3), dtype=np.uint8)
        canvas[:resized_h, :resized_w] = cv2.resize(
            image, (resized_w, resized_h), interpolation=cv2.INTER_AREA
        )
        tensor = canvas.transpose(2, 0, 1)[np.newaxis].astype(np.float32)
        outputs = self._session.run(tensor)

        boxes, landmarks, scores = self._decode(outputs, score_threshold)
        if len(scores) == 0:
            return []
        keep = cv2.dnn.NMSBoxes(
            boxes.tolist(), scores.tolist(), score_threshold, self._nms_threshold, top_k=self._top_k
        )
        detections = []
        for index in np.asarray(keep).reshape(-1):
            x, y, w, h = (boxes[index] / scale).tolist()
            x0, y0 = max(0.0, x), max(0.0, y)
            x1, y1 = min(float(width), x + w), min(float(height), y + h)
            if x1 <= x0 or y1 <= y0:
                continue
            detections.append(
                FaceDetection(
                    x=x0,
                    y=y0,
                    width=x1 - x0,
                    height=y1 - y0,
                    landmarks=(landmarks[index] / scale).astype(np.float32),
                    score=float(scores[index]),
                )
            )
        return detections

    def _decode(
        self, outputs: dict[str, npt.NDArray[np.float32]], score_threshold: float
    ) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32], npt.NDArray[np.float32]]:
        all_boxes, all_landmarks, all_scores = [], [], []
        for stride in _STRIDES:
            cols = self._input_size // stride
            cls = np.clip(outputs[f"cls_{stride}"][0, :, 0], 0.0, 1.0)
            obj = np.clip(outputs[f"obj_{stride}"][0, :, 0], 0.0, 1.0)
            scores = np.sqrt(cls * obj)
            mask = scores >= score_threshold
            if not mask.any():
                continue
            index = np.nonzero(mask)[0]
            col = (index % cols).astype(np.float32)
            row = (index // cols).astype(np.float32)
            bbox = outputs[f"bbox_{stride}"][0][index]
            kps = outputs[f"kps_{stride}"][0][index]
            cx = (col + bbox[:, 0]) * stride
            cy = (row + bbox[:, 1]) * stride
            w = np.exp(bbox[:, 2]) * stride
            h = np.exp(bbox[:, 3]) * stride
            all_boxes.append(np.stack([cx - w / 2, cy - h / 2, w, h], axis=1))
            points = np.empty((len(index), 5, 2), dtype=np.float32)
            points[:, :, 0] = (kps[:, 0::2] + col[:, None]) * stride
            points[:, :, 1] = (kps[:, 1::2] + row[:, None]) * stride
            all_landmarks.append(points)
            all_scores.append(scores[index])
        if not all_scores:
            empty = np.zeros((0,), dtype=np.float32)
            return empty.reshape(0, 4), empty.reshape(0, 5, 2), empty
        return (
            np.concatenate(all_boxes).astype(np.float32),
            np.concatenate(all_landmarks).astype(np.float32),
            np.concatenate(all_scores).astype(np.float32),
        )
