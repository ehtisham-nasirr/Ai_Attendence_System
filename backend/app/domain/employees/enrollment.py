"""Face enrollment (FR-8..FR-10, FR-13, FR-27; standards/14, 18).

Rules, enforced here and nowhere else:
- Enrollment is blocked until the employee's written consent is recorded (§15).
- Each photo is validated by content (JPEG/PNG via Pillow, size limit), re-encoded to strip EXIF,
  then checked by the engine (`/embed`: exactly one face, width, quality, blur).
- At most `enrollment.max_photos` active enrollment photos per employee. Assigned photos from unknown-face
  review have their own limit (`enrollment.max_assigned_photos`, Q64) and do not count here.
- A new embedding very similar to another employee's (cosine > 0.6, FR-10) produces a warning.
- Photos are stored encrypted; embeddings stay AES-256-GCM ciphertext (ADR-0001).
"""

import base64
import io
import logging
from dataclasses import dataclass

import numpy as np
from facetrack_common.constants import CRYPTO_PURPOSE_EMBEDDING, EnrollmentSource
from facetrack_common.models import Employee, FaceEnrollment, User
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import get_cipher
from app.core.db import transaction
from app.core.exceptions import NotFound, ValidationFailed
from app.domain.audit import service as audit
from app.domain.settings import service as settings_service
from app.repositories import employee_repo
from app.schemas.employee import PhotoResult
from app.services import engine_client, storage

logger = logging.getLogger(__name__)

_ALLOWED_FORMATS = {"JPEG", "PNG"}
_MAX_PIXELS = 40_000_000  # refuse decompression bombs


@dataclass(frozen=True)
class IncomingPhoto:
    filename: str
    data: bytes


def sanitise_photo(data: bytes, max_bytes: int) -> bytes:
    """Validates by content and re-encodes as JPEG without metadata (EXIF stripped). Raises ValueError."""
    if len(data) > max_bytes:
        raise ValueError("file_too_large")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in _ALLOWED_FORMATS:
                raise ValueError("unsupported_format")
            if image.width * image.height > _MAX_PIXELS:
                raise ValueError("image_too_large")
            image.load()
            rgb = image.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("invalid_image") from exc
    output = io.BytesIO()
    rgb.save(output, format="JPEG", quality=95)  # no exif/icc passed: metadata is dropped
    return output.getvalue()


def ensure_consent(employee: Employee) -> None:
    if employee.consent_signed_at is None:
        raise ValidationFailed(
            "Enrollment requires the employee's recorded consent.",
            errors={"consent_signed_at": ["Record the signed consent date before enrolling faces."]},
        )


async def find_possible_duplicates(
    db: AsyncSession, employee_id: int, embedding: np.ndarray, model_name: str, threshold: float
) -> list[str]:
    """FR-10: other employees with an enrolled face more similar than `threshold`."""
    cipher = get_cipher()
    matches: set[str] = set()
    query = embedding / max(float(np.linalg.norm(embedding)), 1e-12)
    for code, token, dim in await employee_repo.other_employees_embeddings(db, employee_id, model_name):
        if dim != len(query):
            continue
        other = cipher.decrypt_embedding(token, CRYPTO_PURPOSE_EMBEDDING, dim)
        if float(np.dot(query, other / max(float(np.linalg.norm(other)), 1e-12))) > threshold:
            matches.add(code)
    return sorted(matches)


async def enroll_photos(
    db: AsyncSession,
    employee_id: int,
    photos: list[IncomingPhoto],
    source: EnrollmentSource,
    actor: User,
) -> tuple[list[PhotoResult], int]:
    settings = get_settings()
    values = await settings_service.resolved(db)
    employee = await employee_repo.get(db, employee_id)
    if employee is None:
        raise NotFound("Employee not found.")
    ensure_consent(employee)
    max_photos = int(values["enrollment.max_photos"])
    threshold = float(values["recognition.duplicate_warning_similarity"])
    results: list[PhotoResult] = []
    stored_paths: list[str] = []

    async with transaction(db):
        locked = await employee_repo.get(db, employee_id, for_update=True)
        if locked is None:
            raise NotFound("Employee not found.")
        active = sum(
            1
            for face in await employee_repo.list_faces(db, employee_id)
            if face.is_active and face.source != EnrollmentSource.REVIEW
        )
        for photo in photos:
            name = photo.filename[:120]
            try:
                clean = sanitise_photo(photo.data, settings.max_photo_mb * 1024 * 1024)
            except ValueError as exc:
                results.append(PhotoResult(filename=name, accepted=False, rejection_reason=str(exc)))
                continue
            if active >= max_photos:
                results.append(PhotoResult(filename=name, accepted=False, rejection_reason="too_many_photos"))
                continue
            embed = await engine_client.embed_photo(clean)
            if not embed.accepted or not embed.embedding_encrypted or not embed.embedding_dim:
                results.append(
                    PhotoResult(
                        filename=name,
                        accepted=False,
                        rejection_reason=embed.rejection_reason,
                        quality_score=embed.quality_score,
                        face_width_px=embed.face_width_px,
                    )
                )
                continue
            token = base64.b64decode(embed.embedding_encrypted)
            vector = get_cipher().decrypt_embedding(token, CRYPTO_PURPOSE_EMBEDDING, embed.embedding_dim)
            duplicates = await find_possible_duplicates(db, employee_id, vector, embed.model_name, threshold)
            image_path = storage.new_object_name(f"enroll/{employee_id}", "jpg")
            storage.put_encrypted(image_path, clean)
            stored_paths.append(image_path)
            face = FaceEnrollment(
                employee_id=employee_id,
                image_path=image_path,
                embedding_encrypted=token,
                embedding_dim=embed.embedding_dim,
                model_name=embed.model_name,
                quality_score=float(embed.quality_score or 0.0),
                source=source,
                is_active=True,
            )
            db.add(face)
            await db.flush()
            active += 1
            results.append(
                PhotoResult(
                    filename=name,
                    accepted=True,
                    face_id=face.id,
                    quality_score=face.quality_score,
                    face_width_px=embed.face_width_px,
                    possible_duplicates=duplicates,
                )
            )
        accepted = [r for r in results if r.accepted]
        await audit.record(
            db,
            actor,
            "employee.enroll",
            "employee",
            employee_id,
            new={
                "source": source.value,
                "accepted": len(accepted),
                "rejected": len(results) - len(accepted),
                "possible_duplicates": sorted({c for r in accepted for c in r.possible_duplicates}),
            },
        )
    if any(r.accepted for r in results):
        await engine_client.notify_engines("gallery_reload")
    return results, active


async def delete_face(db: AsyncSession, employee_id: int, face_id: int, actor: User) -> None:
    async with transaction(db):
        face = await employee_repo.get_face(db, employee_id, face_id)
        if face is None:
            raise NotFound("Face enrollment not found.")
        storage.delete_quietly([face.image_path])
        await db.delete(face)  # biometric data: hard delete
        await audit.record(
            db, actor, "employee.face_delete", "employee", employee_id, old={"face_id": face_id}
        )
    await engine_client.notify_engines("gallery_reload")


async def face_image(db: AsyncSession, employee_id: int, face_id: int | None, thumbnail: bool) -> bytes:
    """Decrypted JPEG of one enrollment photo (or the best one when `face_id` is None)."""
    faces = [f for f in await employee_repo.list_faces(db, employee_id) if f.is_active]
    if face_id is not None:
        faces = [f for f in faces if f.id == face_id]
    if not faces:
        raise NotFound("No photo available.")
    best = max(faces, key=lambda f: f.quality_score)
    data = storage.get_decrypted(best.image_path)
    return make_thumbnail(data) if thumbnail else data


def make_thumbnail(jpeg: bytes, size: int = 128) -> bytes:
    with Image.open(io.BytesIO(jpeg)) as image:
        image.thumbnail((size, size))
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=85)
    return output.getvalue()
