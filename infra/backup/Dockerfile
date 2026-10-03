# Nightly encrypted pg_dump (requirements §15/§19: encrypted, kept 30 days, restore tested quarterly).
FROM postgres:16-alpine
# upgrade: security fixes newer than the base image. gosu (the server entrypoint's Go helper, with
# unpatched Go CVEs) is removed: this image only runs pg_dump/pg_restore clients.
RUN apk upgrade --no-cache && apk add --no-cache gnupg tzdata && rm -f /usr/local/bin/gosu
COPY backup.sh restore.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh
ENTRYPOINT ["/usr/local/bin/backup.sh"]
