#!/bin/sh
# Builds alertmanager.yml from the template and the environment, then starts Alertmanager.
# The SMTP password and Teams URL are written to files in the data volume, not the config.
set -eu
umask 077
printf '%s' "${SMTP_PASSWORD:-}" > /alertmanager/smtp_password
teams=""
if [ -n "${TEAMS_WEBHOOK_URL:-}" ]; then
  printf '%s' "$TEAMS_WEBHOOK_URL" > /alertmanager/teams_url
  teams="    msteamsv2_configs:\n      - webhook_url_file: /alertmanager/teams_url\n        send_resolved: true"
fi
sed -e "s|__SMTP_SMARTHOST__|${SMTP_SMARTHOST:-localhost:25}|" \
    -e "s|__SMTP_FROM__|${SMTP_FROM:-facetrack@example.local}|" \
    -e "s|__SMTP_USERNAME__|${SMTP_USERNAME:-}|" \
    -e "s|__ALERT_EMAIL_TO__|${ALERT_EMAIL_TO:-root@localhost}|" \
    -e "s|__TEAMS_BLOCK__|$teams|" \
    /etc/alertmanager/alertmanager.yml.tmpl > /alertmanager/alertmanager.yml
exec /bin/alertmanager --config.file=/alertmanager/alertmanager.yml --storage.path=/alertmanager
