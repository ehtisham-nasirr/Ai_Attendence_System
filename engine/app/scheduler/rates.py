"""What a camera may do right now, given its mode, role and the ladder level (§10.4, standards/17 §2, §7).

Every way the engine spends CPU on a camera is decided here, so all of it sits inside the ladder.
"""

from dataclasses import dataclass

from facetrack_common.constants import ENTRANCE_CAMERA_ROLES, CameraMode, CameraRole, LoadLevel


@dataclass(frozen=True, slots=True)
class RateSettings:
    entrance_fps: float
    general_fps: float
    cooldown_fps: float


@dataclass(frozen=True, slots=True)
class ProcessingPlan:
    detect_fps: float  # 0 = no detection
    keyframes_only: bool  # decoder skips non-key frames
    paused: bool  # shed or outside hours: process nothing
    liveness_low_priority: bool  # step 4: liveness goes to the low-priority lane
    defer_embedding: bool  # step 5: embeddings wait (bounded) until load drops


def plan_processing(
    role: CameraRole,
    mode: CameraMode,
    level: LoadLevel,
    camera_fps: float | None,
    rates: RateSettings,
    in_peak: bool,
) -> ProcessingPlan:
    entrance = role in ENTRANCE_CAMERA_ROLES
    shed = not entrance and level >= LoadLevel.GENERAL_PAUSED
    if mode == CameraMode.PAUSED or shed:
        return ProcessingPlan(0.0, True, True, False, False)

    if entrance:
        fps = camera_fps or rates.entrance_fps
        if level >= LoadLevel.ENTRANCE_REDUCED:
            fps = min(fps, 2.0)  # ladder step 4
    else:
        fps = camera_fps or rates.general_fps
        if level >= LoadLevel.GENERAL_HALF_RATE:
            fps *= 0.5  # ladder step 2
        if in_peak:
            fps *= 0.5  # peak windows: general cameras at reduced rate

    if mode == CameraMode.IDLE:
        detect_fps = 0.0
        # Peak windows keep entrance cameras ACTIVE-ready: full decode so motion is seen on the next frame.
        keyframes_only = not (entrance and in_peak)
    elif mode == CameraMode.COOLDOWN:
        # ~1 FPS detection fits keyframe-only decoding when entrance GOP <= 1 s (§14.2).
        detect_fps = min(fps, rates.cooldown_fps)
        keyframes_only = not (entrance and in_peak)
    else:
        detect_fps = fps
        keyframes_only = False

    return ProcessingPlan(
        detect_fps=detect_fps,
        keyframes_only=keyframes_only,
        paused=False,
        liveness_low_priority=level >= LoadLevel.ENTRANCE_REDUCED,
        defer_embedding=level >= LoadLevel.EMBEDDING_DEFERRED,
    )
