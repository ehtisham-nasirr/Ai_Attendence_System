"""Backend Prometheus metrics (NFR-13). Celery workers report through Redis (`services/metrics_store`)."""

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "facetrack_backend_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "facetrack_backend_http_request_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
WS_CONNECTIONS = Counter("facetrack_backend_ws_connections_total", "WebSocket connections opened")
