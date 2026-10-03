"""Active Directory / LDAP sign-in (FR-40) with ldap3.

Only verifies credentials: the user must already exist in FaceTrack with auth_provider=ldap
(no auto-provisioning, Q19). Bind credentials come from the environment, never from code.
"""

import asyncio
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _verify(username: str, password: str) -> bool:
    from ldap3 import ALL, SUBTREE, Connection, Server  # noqa: PLC0415
    from ldap3.core.exceptions import LDAPException  # noqa: PLC0415
    from ldap3.utils.conv import escape_filter_chars  # noqa: PLC0415

    settings = get_settings()
    if not settings.ldap_server_uri or not password:
        return False
    try:
        server = Server(settings.ldap_server_uri, get_info=ALL, connect_timeout=5)
        with Connection(
            server, settings.ldap_bind_dn, settings.ldap_bind_password.get_secret_value(), auto_bind=True
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
        with Connection(server, user_dn, password, auto_bind=True):
            return True
    except LDAPException as exc:
        logger.warning("directory sign-in failed", extra={"error": type(exc).__name__})
        return False


async def verify_credentials(username: str, password: str) -> bool:
    return await asyncio.to_thread(_verify, username, password)
