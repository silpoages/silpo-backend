# silpo-backend

Server-side API for Silpo: FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL, managed with `uv`.

> This repository is server-side only (API + PostgreSQL). The mobile app's SQLite database
> lives in a separate repository and is out of scope here.

## Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI |
| ORM | SQLAlchemy 2.0 (async) |
| Validation | Pydantic v2 |
| Migrations | Alembic (async) |
| PostgreSQL driver | asyncpg |
| Tests | pytest + pytest-asyncio + testcontainers |
| Dependency manager | uv |
| Linter / formatter | Ruff |
| Git hooks | Husky |

## Project layout

```
app/
  api/routes/   # HTTP endpoints (request/response only, no business logic)
  core/         # settings/config
  db/           # engine, session, declarative base
  models/       # SQLAlchemy models
  schemas/      # Pydantic schemas
  services/     # business logic / data access, called by routes
  main.py       # FastAPI app entrypoint
alembic/        # migrations
tests/          # pytest + testcontainers integration tests
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package/dependency manager)
- [Docker](https://docs.docker.com/get-docker/) + Docker Compose v2 (`docker compose`)
- [Node.js](https://nodejs.org/) 18+ (only used to run Husky git hooks, no JS app code lives here)

Install `uv`:

**Linux / macOS**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell)**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Setup

1. Copy the environment file and adjust if needed:

   **Linux / macOS**
   ```bash
   cp .env.example .env
   ```

   **Windows (PowerShell)**
   ```powershell
   Copy-Item .env.example .env
   ```

2. Install dependencies (creates `.venv` and resolves/writes `uv.lock`):

   ```bash
   uv sync
   ```

3. Install git hooks (Husky). This works the same on Linux, macOS, and Windows (via Git Bash,
   which ships with Git for Windows):

   ```bash
   npm install
   ```

## Running with Docker (recommended)

Works identically on Windows, Linux, and macOS — no bind mounts, uses named volumes.

```bash
docker compose up --build
```

This starts PostgreSQL (waits for its healthcheck) and the API, running `alembic upgrade head`
automatically before the server starts. The API is available at http://localhost:8000
(docs at http://localhost:8000/docs).

Stop and remove containers:
```bash
docker compose down
```

Stop and also wipe the database volume:
```bash
docker compose down -v
```

## Running locally (without Docker for the API)

1. Start only PostgreSQL via Docker:
   ```bash
   docker compose up -d db
   ```
2. Make sure `.env` has `POSTGRES_HOST=localhost`.
3. Apply migrations:
   ```bash
   uv run alembic upgrade head
   ```
4. Run the API with reload:
   ```bash
   uv run uvicorn app.main:app --reload
   ```

## Migrations

Create a new migration after changing models in `app/models/`:
```bash
uv run alembic revision --autogenerate -m "describe change"
```

Apply migrations:
```bash
uv run alembic upgrade head
```

Roll back the last migration:
```bash
uv run alembic downgrade -1
```

## Tests

Integration tests spin up a real PostgreSQL instance via **testcontainers**, so Docker must be
running. No other setup is required — migrations run automatically against the ephemeral
container.

```bash
uv run pytest
```

This works the same way on Windows (with Docker Desktop running), Linux, and macOS.

## Linting

```bash
uv run ruff check .
uv run ruff format --check .
```

Auto-fix / auto-format:

```bash
uv run ruff check --fix .
uv run ruff format .
```

## Git hooks (Husky)

After `npm install`, a `pre-commit` hook runs `ruff check` and `ruff format --check` on every
commit and blocks it if either fails. Hooks live in [.husky/](.husky/) as plain POSIX shell
scripts, executed via Git's own hook mechanism (`core.hooksPath`) — this works identically on
Linux, macOS, and Windows (Git for Windows bundles Git Bash, which provides the `sh` these
scripts run under). No native Windows-specific setup is required.

## CI

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs on every push and pull request:

- **Lint** — `ruff check` + `ruff format --check`
- **Test** — `pytest` (testcontainers spins up PostgreSQL inside the runner)
- **Build** — builds the Docker image (runs only if lint and test pass)

All three jobs must pass before a PR can be merged. To enforce this as a hard block, add them as
required status checks in the repository's branch protection settings (Settings → Branches →
Branch protection rules → `main`).

## Example endpoint

A minimal `Template` CRUD is included at `/templates` to validate the API → SQLAlchemy →
PostgreSQL path end-to-end. Rename/replace it with your first real entity.

- `POST /templates`
- `GET /templates`
- `GET /templates/{id}`
- `PATCH /templates/{id}`
- `DELETE /templates/{id}`
- `GET /health`
