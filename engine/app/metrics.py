"""Prometheus metrics of the engine (NFR-13, standards/17 §7, §10). Exposed at `/metrics`.

Labels never carry biometric or personal data — only camera ids, steps and statuses.
"""

from prometheus_client import Counter, Gauge, Histogram

CPU_PERCENT = Gauge("facetrack_engine_cpu_percent", "Node CPU usage sampled by the load monitor")
LOAD_LEVEL = Gauge("facetrack_engine_load_level", "Current degradation ladder step (1 = normal)")
LADDER_CHANGES = Counter("facetrack_engine_ladder_changes_total", "Degradation ladder step changes")
MAX_LAG = Gauge("facetrack_engine_max_lag_seconds", "Largest camera processing lag")
QUEUE_DEPTH = Gauge("facetrack_engine_inference_queue_depth", "Requests waiting per lane", ["lane"])
GALLERY_SIZE = Gauge("facetrack_engine_gallery_embeddings", "Embeddings loaded in the gallery")
GALLERY_EMPLOYEES = Gauge("facetrack_engine_gallery_employees", "Employees loaded in the gallery")
WORKER_RESTARTS = Counter("facetrack_engine_worker_restarts_total", "Inference worker restarts")
CAMERA_RESTARTS = Counter("facetrack_engine_camera_restarts_total", "Camera process restarts", ["camera_id"])

CAMERA_MODE = Gauge("facetrack_engine_camera_mode", "1 for the camera's current mode", ["camera_id", "mode"])
CAMERA_CONNECTED = Gauge("facetrack_engine_camera_connected", "Stream connected (1/0)", ["camera_id"])
CAMERA_FPS = Gauge("facetrack_engine_camera_fps", "Processed frames per second", ["camera_id"])
CAMERA_FPS_TARGET = Gauge("facetrack_engine_camera_fps_target", "Planned detection rate", ["camera_id"])
CAMERA_LAG = Gauge("facetrack_engine_camera_lag_seconds", "Frame age when detection returned", ["camera_id"])
CAMERA_FRAME_AGE = Gauge(
    "facetrack_engine_camera_last_frame_age_seconds", "Seconds since the last processed frame", ["camera_id"]
)
CAMERA_BUFFERED = Gauge(
    "facetrack_engine_buffered_events", "Events waiting in the disk buffer", ["camera_id"]
)
CAMERA_DEFERRED = Gauge(
    "facetrack_engine_deferred_embeddings", "Embeddings deferred (ladder step 5)", ["camera_id"]
)
CAMERA_LOST = Gauge(
    "facetrack_engine_lost_events", "Events refused by a full buffer (must stay 0)", ["camera_id"]
)
UNCONFIRMED_KNOWN_TRACKS = Counter(
    "facetrack_engine_unconfirmed_known_tracks_total",
    "Unconfirmed tracks that matched only one enrolled employee; not logged as Unknown (FR-17)",
    ["camera_id"],
)
CAMERA_COUNTS = Counter(
    "facetrack_engine_camera_counts_total", "Per-camera pipeline counters", ["camera_id", "name"]
)
STEP_MS = Histogram(
    "facetrack_engine_step_milliseconds",
    "Per-step processing time",
    ["step"],
    buckets=(0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000),
)
