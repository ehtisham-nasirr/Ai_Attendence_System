#!/bin/sh
# Runs once, when the database volume is created. The engine nodes only read cameras, enrollments and
# settings (standards/17), so they get a read-only role; tables created later by Alembic (as the
# facetrack owner) are covered through default privileges.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v engine_password="$ENGINE_DB_PASSWORD" <<'SQL'
CREATE ROLE facetrack_engine LOGIN PASSWORD :'engine_password';
GRANT CONNECT ON DATABASE facetrack TO facetrack_engine;
GRANT USAGE ON SCHEMA public TO facetrack_engine;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO facetrack_engine;
ALTER DEFAULT PRIVILEGES FOR ROLE facetrack IN SCHEMA public GRANT SELECT ON TABLES TO facetrack_engine;
CREATE EXTENSION IF NOT EXISTS vector;
SQL
