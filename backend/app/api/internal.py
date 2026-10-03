"""Endpoints for other internal services only (not proxied by Nginx)."""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.domain.cameras.service import verify_live_token

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.post("/mediamtx/auth")
async def mediamtx_auth(request: Request) -> Response:
    """MediaMTX external authentication: allow `read` of a camera path only with a valid live token."""
    body: dict[str, Any] = await request.json()
    if body.get("action") != "read":
        return Response(status_code=401)
    path = str(body.get("path", ""))
    token = str(body.get("token") or "")
    if not token:
        query = str(body.get("query") or "")
        token = next((part[6:] for part in query.split("&") if part.startswith("token=")), "")
    return Response(status_code=200 if token and verify_live_token(token, path) else 401)
