"""Model metadata tests (requirements §11)."""

from facetrack_common.models import Base

EXPECTED_TABLES = {
    "locations",
    "departments",
    "shifts",
    "employees",
    "face_enrollments",
    "cameras",
    "recognition_events",
    "unknown_faces",
    "attendance_days",
    "attendance_corrections",
    "holidays",
    "leaves",
    "users",
    "api_clients",
    "settings",
    "audit_logs",
}


def test_sixteen_tables_of_section_11() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_table_has_id_and_timestamps() -> None:
    for table in Base.metadata.tables.values():
        assert {"id", "created_at", "updated_at"} <= set(table.columns.keys()), table.name


def test_recognition_events_is_partitioned_and_keyed_on_captured_at() -> None:
    table = Base.metadata.tables["recognition_events"]
    assert table.dialect_options["postgresql"]["partition_by"] == "RANGE (captured_at)"
    assert {c.name for c in table.primary_key.columns} == {"id", "captured_at"}


def test_biometric_tables_have_no_soft_delete() -> None:
    for name in ("face_enrollments", "unknown_faces"):
        assert "deleted_at" not in Base.metadata.tables[name].columns


def test_no_plaintext_embedding_columns() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if "embedding" in column.name:
                assert column.name in {"embedding_encrypted", "embedding_dim"}, (table.name, column.name)
