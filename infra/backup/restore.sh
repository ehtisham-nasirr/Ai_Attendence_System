#!/bin/sh
# Restores an encrypted backup into a database (quarterly restore test, docs/runbook.md).
#   restore.sh /backups/facetrack-20261004-0130.dump.gpg facetrack_restore_test
# Never point this at the live database unless that is the intent.
set -euo pipefail
: "${BACKUP_ENCRYPTION_KEY:?BACKUP_ENCRYPTION_KEY is required}"
file="${1:?backup file}"
database="${2:?target database (it is created if missing)}"
createdb "$database" 2>/dev/null || true
psql -d "$database" -c "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null
gpg --batch --quiet --decrypt --passphrase-fd 3 "$file" 3<<KEY | pg_restore --no-owner --exit-on-error -d "$database"
$BACKUP_ENCRYPTION_KEY
KEY
echo "restored $file into $database"
psql -d "$database" -At -c "SELECT 'employees: ' || count(*) FROM employees UNION ALL SELECT 'attendance_days: ' || count(*) FROM attendance_days"
