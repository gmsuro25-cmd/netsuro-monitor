# First checkpoint: API and PostgreSQL

## The problem we are solving

Before monitoring other systems, Netsuro must confirm that its own HTTP process
is running and that it can communicate with its dependencies.

## Two different health concepts

`GET /health/live` confirms that the API process is running. It does not query
any dependency.

`GET /health/ready` confirms that PostgreSQL and Redis respond to minimal
operations. The API may still be alive when a dependency fails, but it is not
ready to handle operations that require that dependency.

Keeping these states separate lets us distinguish between:

- The process is not running.
- The process is running, but a dependency is unavailable.
- The process and its required dependencies are operational.

## Responsibility of the main files

- `compose.yml`: defines the services and their connections.
- `.env.example`: documents required configuration without real secrets.
- `api/Dockerfile`: builds the shared Python application image.
- `api/requirements.txt`: pins Python dependencies.
- `api/app/main.py`: defines the HTTP API and its endpoints.
- `api/app/database.py`: centralizes PostgreSQL operations.
- `api/app/queue.py`: manages Redis Streams, locks, and temporary heartbeats.
- `api/migrations/`: contains versioned database schema changes.

This checkpoint established the health foundation used by the monitoring,
incident, history, and notification features added later.
