#!/bin/sh
# Waits until BACKUP_TIME each day, then writes /backups/facetrack-<stamp>.dump.gpg:
# pg_dump custom format, encrypted with AES-256 (gpg symmetric, integrity-protected) using
# BACKUP_ENCRYPTION_KEY. Old backups beyond BACKUP_KEEP_DAYS are deleted. The result is exported for
# Prometheus through node-exporter's textfile collector (alert "BackupFailed").
#   backup.sh --now   run once immediately (used by the runbook and before production deploys)
set -euo pipefail
umask 077  # backups and the partial file are readable by their owner only

: "${BACKUP_ENCRYPTION_KEY:?BACKUP_ENCRYPTION_KEY is required}"
BACKUP_TIME="${BACKUP_TIME:-01:30}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
TEXTFILE=/textfile/facetrack_backup.prom

metric() {
  # $1 = 1 success / 0 failure, $2 = size in bytes
  now=$(date +%s)
  {
    echo "# HELP facetrack_backup_last_run_timestamp_seconds Unix time of the last backup attempt"
    echo "# TYPE facetrack_backup_last_run_timestamp_seconds gauge"
    echo "facetrack_backup_last_run_timestamp_seconds $now"
    echo "# HELP facetrack_backup_last_run_success 1 if the last backup succeeded"
    echo "# TYPE facetrack_backup_last_run_success gauge"
    echo "facetrack_backup_last_run_success $1"
    if [ "$1" = 1 ]; then
      echo "# HELP facetrack_backup_last_success_timestamp_seconds Unix time of the last successful backup"
      echo "# TYPE facetrack_backup_last_success_timestamp_seconds gauge"
      echo "facetrack_backup_last_success_timestamp_seconds $now"
      echo "# HELP facetrack_backup_size_bytes Size of the last successful backup"
      echo "# TYPE facetrack_backup_size_bytes gauge"
      echo "facetrack_backup_size_bytes $2"
    elif [ -f "$TEXTFILE" ]; then
      grep -E '^facetrack_backup_(last_success_timestamp_seconds|size_bytes) ' "$TEXTFILE" || true
    fi
  } > "$TEXTFILE.tmp"
  chmod 644 "$TEXTFILE.tmp"  # node-exporter reads it as another user; it holds no secrets
  mv "$TEXTFILE.tmp" "$TEXTFILE"
}

run_backup() {
  stamp=$(date +%Y%m%d-%H%M)
  target="/backups/facetrack-$stamp.dump.gpg"
  echo "$(date -Iseconds) backup started -> $target"
  if pg_dump --format=custom --no-owner \
      | gpg --batch --yes --quiet --symmetric --cipher-algo AES256 \
            --passphrase-fd 3 --output "$target.partial" 3<<KEY
$BACKUP_ENCRYPTION_KEY
KEY
  then
    mv "$target.partial" "$target"
    size=$(stat -c %s "$target")
    find /backups -name 'facetrack-*.dump.gpg' -mtime "+$BACKUP_KEEP_DAYS" -delete
    metric 1 "$size"
    echo "$(date -Iseconds) backup finished ($size bytes)"
  else
    rm -f "$target.partial"
    metric 0 0
    echo "$(date -Iseconds) backup FAILED" >&2
    return 1
  fi
}

if [ "${1:-}" = "--now" ]; then
  run_backup
  exit $?
fi

mkdir -p /backups /textfile
while true; do
  now=$(date +%s)
  next=$(date -d "$(date +%Y-%m-%d) $BACKUP_TIME" +%s 2>/dev/null || date -D '%Y-%m-%d %H:%M' -d "$(date +%Y-%m-%d) $BACKUP_TIME" +%s)
  [ "$next" -le "$now" ] && next=$((next + 86400))
  echo "$(date -Iseconds) next backup in $(( (next - now) / 60 )) minutes"
  sleep $((next - now))
  run_backup || true
done
