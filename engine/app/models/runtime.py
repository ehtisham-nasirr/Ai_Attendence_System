"""CPU inference sessions with a fixed thread budget (standards/17 §4, §5).

OpenVINO is the primary runtime; ONNX Runtime is the alternative. Only CPU devices/providers are
ever selected — never GPU and never ONNX Runtime's remote (Azure) provider (CLAUDE.md §1.3).
"""

from pathlib import Path
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt

RuntimeName = Literal["openvino", "onnxruntime"]
PrecisionHint = Literal["f32", "bf16"]
Tensor = npt.NDArray[np.float32]


class InferenceSession(Protocol):
    input_name: str
    input_shape: tuple[int, ...]

    def run(self, tensor: Tensor) -> dict[str, Tensor]:
        """Runs one forward pass; returns outputs by name."""
        ...


class OnnxRuntimeSession:
    def __init__(self, model_path: Path, threads: int) -> None:
        import onnxruntime as ort  # noqa: PLC0415  # imported in worker processes only

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.log_severity_level = 3
        self._session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        model_input = self._session.get_inputs()[0]
        self.input_name: str = model_input.name
        self.input_shape: tuple[int, ...] = tuple(d if isinstance(d, int) else -1 for d in model_input.shape)
        self._output_names: list[str] = [o.name for o in self._session.get_outputs()]

    def run(self, tensor: Tensor) -> dict[str, Tensor]:
        outputs = self._session.run(self._output_names, {self.input_name: tensor})
        return dict(zip(self._output_names, outputs, strict=True))


class OpenVinoSession:
    def __init__(self, model_path: Path, threads: int, precision: PrecisionHint = "f32") -> None:
        import openvino as ov  # noqa: PLC0415  # imported in worker processes only

        core = ov.Core()
        compiled = core.compile_model(
            str(model_path),
            "CPU",
            {
                "INFERENCE_NUM_THREADS": threads,
                "NUM_STREAMS": 1,
                "PERFORMANCE_HINT": "LATENCY",
                "ENABLE_CPU_PINNING": True,
                # On AMX/AVX-512-bf16 Xeons OpenVINO defaults to bf16, which measurably shifts landmarks
                # and embeddings; f32 is the default (accuracy first, NFR-2). INT8 models are produced
                # and evaluated separately (scripts/convert_int8.py).
                "INFERENCE_PRECISION_HINT": precision,
            },
        )
        self._request = compiled.create_infer_request()
        model_input = compiled.inputs[0]
        self.input_name = model_input.get_any_name()
        partial = model_input.get_partial_shape()
        self.input_shape = tuple(d.get_length() if d.is_static else -1 for d in partial)
        # An output can have several tensor names (e.g. "291" and "cls_8"); expose all of them so callers
        # can use the original ONNX output names.
        self._outputs = [(o, sorted(o.get_names())) for o in compiled.outputs]

    def run(self, tensor: Tensor) -> dict[str, Tensor]:
        result = self._request.infer({0: tensor})
        named: dict[str, Tensor] = {}
        for port, names in self._outputs:
            value = np.asarray(result[port])
            for name in names:
                named[name] = value
        return named


def create_session(
    model_path: Path, runtime: RuntimeName, threads: int, precision: PrecisionHint = "f32"
) -> InferenceSession:
    if not model_path.is_file():
        raise FileNotFoundError(
            f"Model file not found: {model_path}. Run scripts/download_models.py (models are never in Git)."
        )
    if runtime == "openvino":
        return OpenVinoSession(model_path, threads, precision)
    return OnnxRuntimeSession(model_path, threads)
