"""Engine API dependencies: shared-token check and supervisor access."""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.scheduler.supervisor import EngineSupervisor


def get_supervisor(request: Request) -> EngineSupervisor:
    supervisor: EngineSupervisor = request.app.state.supervisor
    return supervisor


def require_token(request: Request, x_engine_token: Annotated[str | None, Header()] = None) -> None:
    """The engine API is internal-only; the backend also proves itself with a shared token."""
    expected = request.app.state.settings.api_token.get_secret_value()
    if x_engine_token is None or not hmac.compare_digest(x_engine_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid engine token.")


SupervisorDep = Annotated[EngineSupervisor, Depends(get_supervisor)]
