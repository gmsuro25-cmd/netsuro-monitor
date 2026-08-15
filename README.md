# Netsuro Monitor

An educational monitoring platform for websites, APIs, background jobs, and
Netsuro's own internal services. It records availability and latency, detects
incidents, receives heartbeats, and sends Slack notifications.

## Architecture

- **web**: Nginx dashboard and reverse proxy.
- **api**: FastAPI HTTP API.
- **postgres**: persistent monitors, checks, incidents, history, and notifications.
- **redis**: check queue, locks, and temporary component heartbeats.
- **scheduler**: schedules HTTP checks and records internal health samples.
- **worker**: performs queued HTTP checks.
- **notifier**: sends incident notifications to Slack with retries.
- **maintenance**: removes expired sessions and old unreferenced raw samples.
- **backup**: creates daily PostgreSQL dumps and keeps 14 days by default.
- **migrate**: applies Alembic database migrations before the application starts.

The dashboard and administrative API require an authenticated administrator.
Heartbeat receivers and the liveness endpoint remain public.

HTTP monitors allow ports 80 and 443 by default and reject loopback, private,
link-local, multicast, unspecified, and reserved destination addresses. Every
redirect is validated before it is followed. `MONITOR_ALLOWED_PRIVATE_HOSTS`
can explicitly allow a named private service for a trusted installation, but
loopback and link-local/cloud-metadata addresses are always blocked.

Redis-backed rate limits protect login attempts, public heartbeats, manual
checks, authenticated reads, and administrative writes. Identifiers and secret
tokens are hashed before they become Redis keys. Login and heartbeat requests
fail closed with HTTP 503 when Redis is unavailable; other authenticated routes
remain available so an administrator can inspect the outage.

Production validates the browser `Origin` on every state-changing administrative
request and rejects unexpected `Host` headers. Heartbeats are exempt from Origin
validation because they are authenticated by their secret URL and are commonly
sent by non-browser workers. Nginx adds a Content Security Policy and browser
security headers to every response.

## Local setup

```bash
cp .env.example .env
docker compose up -d --build
```

Docker automatically combines `compose.yml` with `compose.override.yml` on the
developer machine. The override publishes the dashboard and API only on the
Mac's loopback interface, so they are not reachable by other devices on the
local network.

Local services:

- Dashboard: `http://localhost:3000`
- API: `http://localhost:8000`
- Interactive API documentation: `http://localhost:8000/docs`
- Liveness: `GET http://localhost:8000/health/live`
- Readiness: `GET http://localhost:8000/health/ready`

Stop the services without deleting stored data:

```bash
docker compose down
```

Run the automated test suite in the same Python environment used by the API:

```bash
docker compose run --rm api pytest -q
```

The local API image uses the Dockerfile `test` target and includes pytest and
the test suite. Production uses the smaller `runtime` target, which contains
neither pytest nor test files.

The `.env` file contains local secrets and is ignored by Git. Never commit the
Slack webhook URL or real database credentials.

## Production configuration

Production deliberately does not use the local override. Create its private
environment file from the production template:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Replace every `CHANGE_ME` value, then validate the merged configuration:

```bash
docker compose --env-file .env.production \
  -f compose.yml -f compose.production.yml config --quiet
```

Start production with the same explicit file combination:

```bash
docker compose --env-file .env.production \
  -f compose.yml -f compose.production.yml up -d --build
```

In this configuration the API has no host port and the web container listens
only on `127.0.0.1:3000`. A later HTTPS reverse proxy will be the sole public
entry point. `COOKIE_SECURE=true` means authentication cookies will only travel
over HTTPS.

All containers rotate Docker JSON logs at 10 MB and retain three files. Local
resource limits are intentionally generous. Production applies tighter CPU,
memory, and process limits; Python services run as an unprivileged user with a
read-only root filesystem, all Linux capabilities dropped, and
`no-new-privileges` enabled.

Production credentials are Docker secrets rather than container environment
values. Create `secrets/postgres_password.txt`, `secrets/admin_password.txt`, and
`secrets/slack_webhook_url.txt` on the server, put one raw value in each file,
and run `chmod 600 secrets/*.txt`. Applications receive only the corresponding
`/run/secrets/...` path. Local development continues to read the existing
values from `.env`.

## Retention and backups

Raw monitor checks and internal health samples are kept for 90 days by default.
Checks referenced by incidents are always preserved. Expired sessions and sent
notification records older than 90 days are removed automatically.

List available database backups:

```bash
docker compose run --rm backup sh -c 'ls -lh /backups'
```

Verify the latest backup by restoring it into a temporary database:

```bash
docker compose run --rm backup /scripts/verify-backup.sh
```

The verification command never overwrites the Netsuro database. Local backup
volumes protect against database corruption, but production backups must also be
copied to another server or object-storage provider.

The authenticated dashboard shows backup count, total size, retention, the five
most recent files, and the latest successful restore verification. Restores are
intentionally not available as a dashboard action because they can overwrite
data and should remain an explicit administrative operation.

## Roadmap

- Add Server-Sent Events (SSE) for near-real-time dashboard updates.
- Show `Live`, `Reconnecting`, and `Offline` connection states.
- Keep the current 30-second polling cycle as a fallback when SSE disconnects.
