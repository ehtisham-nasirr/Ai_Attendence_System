"""API keys for the HR/payroll system (FR-34). The full key is returned once; only a hash is stored."""

from facetrack_common.models import ApiClient, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import transaction
from app.core.exceptions import NotFound
from app.core.security import generate_api_key, hash_api_key
from app.domain.audit import service as audit
from app.repositories.base import apply_changes, get_live, soft_delete
from app.schemas.integration import ApiClientCreate, ApiClientOut, ApiClientUpdate


def to_out(client: ApiClient) -> ApiClientOut:
    return ApiClientOut.model_validate(client)


async def list_clients(db: AsyncSession) -> list[ApiClient]:
    stmt = select(ApiClient).where(ApiClient.deleted_at.is_(None)).order_by(ApiClient.name)
    return list((await db.scalars(stmt)).all())


async def create_client(db: AsyncSession, payload: ApiClientCreate, actor: User) -> tuple[ApiClient, str]:
    key, prefix = generate_api_key()
    async with transaction(db):
        client = ApiClient(
            name=payload.name,
            key_prefix=prefix,
            key_hash=hash_api_key(key),
            scopes=list(payload.scopes),
            is_active=True,
        )
        db.add(client)
        await db.flush()
        # The key itself is never written to the audit log.
        await audit.record(db, actor, "api_client.create", "api_client", client.id, new=payload.model_dump())
    return client, key


async def update_client(db: AsyncSession, client_id: int, payload: ApiClientUpdate, actor: User) -> ApiClient:
    async with transaction(db):
        client = await get_live(db, ApiClient, client_id, for_update=True)
        if client is None:
            raise NotFound("API client not found.")
        changes = payload.model_dump(exclude_unset=True)
        old = apply_changes(client, changes)
        await audit.record(db, actor, "api_client.update", "api_client", client_id, old=old, new=changes)
    return client


async def revoke_client(db: AsyncSession, client_id: int, actor: User) -> None:
    async with transaction(db):
        client = await get_live(db, ApiClient, client_id, for_update=True)
        if client is None:
            raise NotFound("API client not found.")
        client.is_active = False
        soft_delete(client)
        await audit.record(db, actor, "api_client.revoke", "api_client", client_id)
