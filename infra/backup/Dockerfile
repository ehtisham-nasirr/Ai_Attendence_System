# Nightly encrypted pg_dump (requirements §15/§19: encrypted, kept 30 days, restore tested quarterly).
FROM postgres:16-alpine
RUN apk add --no-cache gnupg tzdata
COPY backup.sh restore.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh
ENTRYPOINT ["/usr/local/bin/backup.sh"]
