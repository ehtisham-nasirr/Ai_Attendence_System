"""Active Directory / LDAP sign-in (FR-40) with ldap3.

Only verifies credentials: the user must already exist in FaceTrack with auth_provider=ldap
(no auto-provisioning, Q19). Bind credentials come from the environment, never from code.
"""

import asyncio
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _server(uri: str) -> Any:
    from ldap3 import ALL, Server  # noqa: PLC0415

    return Server(uri, get_info=ALL, connect_timeout=5)


def _connect(server: Any, user: str, password: str) -> Any:
    """Bound connection (raises LDAPException on bad credentials). Tests swap in ldap3's mock strategy."""
    from ldap3 import Connection  # noqa: PLC0415

    return Connection(server, user, password, auto_bind=True)


def _verify(username: str, password: str) -> bool:
    from ldap3 import SUBTREE  # noqa: PLC0415
    from ldap3.core.exceptions import LDAPException  # noqa: PLC0415
    from ldap3.utils.conv import escape_filter_chars  # noqa: PLC0415

    settings = get_settings()
    if not settings.ldap_server_uri or not password:
        return False
    try:
        server = _server(settings.ldap_server_uri)
        with _connect(
            server, settings.ldap_bind_dn, settings.ldap_bind_password.get_secret_value()
        ) as service:
            service.search(
                settings.ldap_base_dn,
                f"({settings.ldap_user_attribute}={escape_filter_chars(username)})",
                search_scope=SUBTREE,
                attributes=["distinguishedName"],
                size_limit=2,
            )
            if len(service.entries) != 1:
                return False
            user_dn = service.entries[0].entry_dn
        with _connect(server, user_dn, password):
            return True
    except LDAPException as exc:
        logger.warning("directory sign-in failed", extra={"error": type(exc).__name__})
        return False


async def verify_credentials(username: str, password: str) -> bool:
    return await asyncio.to_thread(_verify, username, password)
