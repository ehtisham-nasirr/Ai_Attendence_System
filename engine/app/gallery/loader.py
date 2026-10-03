"""Loads the enrolled gallery from PostgreSQL (FR-19).

Only active enrollments of active, non-deleted employees, made with the current embedder model, are
loaded — so deactivating an employee removes them at the next reload (FR-13). Embeddings are decrypted
in memory only.
"""

import numpy as np
from facetrack_common.constants import CRYPTO_PURPOSE_EMBEDDING, EmployeeStatus
from facetrack_common.crypto import Cipher
from facetrack_common.models import Employee, FaceEnrollment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gallery.index import GallerySnapshot
from app.models.base import l2_normalise


async def load_gallery(
    sessions: async_sessionmaker[AsyncSession], cipher: Cipher, model_name: str, dim: int, version: int
) -> GallerySnapshot:
    stmt = (
        select(Employee.employee_code, FaceEnrollment.embedding_encrypted, FaceEnrollment.embedding_dim)
        .join(Employee, Employee.id == FaceEnrollment.employee_id)
        .where(
            FaceEnrollment.is_active.is_(True),
            FaceEnrollment.model_name == model_name,
            Employee.status == EmployeeStatus.ACTIVE,
            Employee.deleted_at.is_(None),
        )
        .order_by(FaceEnrollment.id)
    )
    async with sessions() as session:
        rows = (await session.execute(stmt)).all()
    codes: list[str] = []
    vectors = []
    for code, token, stored_dim in rows:
        if stored_dim != dim:
            continue  # never compare embeddings across models/dimensions
        vectors.append(cipher.decrypt_embedding(token, CRYPTO_PURPOSE_EMBEDDING, dim))
        codes.append(code)
    matrix = l2_normalise(np.stack(vectors)) if vectors else np.zeros((0, dim), dtype=np.float32)
    return GallerySnapshot(model_name=model_name, version=version, employee_codes=codes, vectors=matrix)
