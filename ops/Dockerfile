FROM alpine:3.24.1

RUN apk add --no-cache postgresql16-client

COPY backup.sh /scripts/backup.sh
COPY verify-backup.sh /scripts/verify-backup.sh
RUN chmod +x /scripts/backup.sh /scripts/verify-backup.sh

CMD ["/scripts/backup.sh"]
