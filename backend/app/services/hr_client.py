"""Generic JSON client for the HR system (FR-12, FR-24; Q32). The real system is unknown (P6), so the
expected shape is documented in backend/README.md and kept in this one module.

GET {base}/employees -> list (or {"data": [...], "next": url}) of employee records
GET {base}/leaves?from=YYYY-MM-DD&to=YYYY-MM-DD -> list of approved leave records
"""

from datetime import date
from typing import Any

import httpx

from app.core.config import get_settings

MAX_PAGES = 200


class HrSystemError(Exception):
    pass


def _client(base_url: str) -> httpx.Client:
    token = get_settings().hr_api_token.get_secret_value()
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=30.0)


def _collect(client: httpx.Client, path: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Follows `next` links when the response is paginated."""
    items: list[dict[str, Any]] = []
    url: str | None = path
    for _ in range(MAX_PAGES):
        if url is None:
            return items
        try:
            response = client.get(url, params=params if url == path else None)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HrSystemError(f"HR system request failed: {type(exc).__name__}") from exc
        if isinstance(body, list):
            return items + [i for i in body if isinstance(i, dict)]
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise HrSystemError("HR system returned an unexpected response shape.")
        items.extend(i for i in body["data"] if isinstance(i, dict))
        next_url = body.get("next")
        url = str(next_url) if next_url else None
    raise HrSystemError("HR system pagination did not end.")


def fetch_employees(base_url: str) -> list[dict[str, Any]]:
    with _client(base_url) as client:
        return _collect(client, "/employees")


def fetch_leaves(base_url: str, date_from: date, date_to: date) -> list[dict[str, Any]]:
    with _client(base_url) as client:
        return _collect(client, "/leaves", {"from": date_from.isoformat(), "to": date_to.isoformat()})
