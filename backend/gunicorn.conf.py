"""Gunicorn with Uvicorn workers for the API container (requirements §18)."""

import os

bind = "0.0.0.0:8000"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
# Long enough for photo enrollment (engine /embed calls); WebSockets are not affected by this timeout.
timeout = 120
graceful_timeout = 30
keepalive = 5
# Requests are logged as JSON by the app middleware; Gunicorn's own access log would duplicate them.
accesslog = None
errorlog = "-"
# Nginx is the only client and sets X-Forwarded-For / X-Forwarded-Proto.
forwarded_allow_ips = "*"
# Gunicorn's runtime control socket (gunicornc) is not used; it would also need a home directory that
# the unprivileged container user does not have.
control_socket_disable = True
