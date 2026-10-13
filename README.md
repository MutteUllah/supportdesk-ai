# SupportDesk AI

A customer support SaaS implementation with a FastAPI API, Next.js dashboard, iframe widget, PostgreSQL/pgvector, Celery/Redis ingestion, and S3-compatible storage. The default **mock mode uses deterministic text extraction, not LLM inference**.

## Start with Docker

Requires Docker Engine/Desktop with Compose v2 and approximately 4 GB free memory. From this directory:

```sh
cp .env.example .env
# On PowerShell: Copy-Item .env.example .env
# Edit .env: choose DEMO_PASSWORD (12+ characters) if you want demo accounts.
docker compose up --build -d --wait
docker compose exec api python -m app.seed
```

Startup runs migrations and creates the local storage bucket. Demo seeding is explicit, repeatable, and refused in production. Seeding prints the public workspace IDs and queues real Celery jobs. Wait for the documents to show **ready** in the dashboard.

| Interface | Address |
|---|---|
| Business dashboard | http://localhost:3000 |
| Separate widget demo | http://localhost:3001 |
| API documentation | http://localhost:8000/docs |
| Liveness / readiness | http://localhost:8000/health · http://localhost:8000/ready |
| Local MinIO console | http://localhost:9001 |

Use `localhost` consistently; `127.0.0.1` is a different allowed origin. Sign in as `northstar@example.test` or `cedar@example.test` with your configured `DEMO_PASSWORD`. Each account owns a separate business. You can also register a new account and create workspaces.

Northstar ships in **3 business days** and accepts returns within **30 days**. Cedar & Clay ships in **12 business days**, accepts returns within **7 days**, and excludes custom items. These are fictional demo policies.

Open Settings, copy the public workspace ID from the embed snippet, and paste it into the demo website. The seed permits `http://localhost:3001`. Ask about shipping, open a citation, request a human, then claim the conversation in the dashboard **Support inbox**. Human replies appear through polling. Return it to the bot when finished.

## What is implemented

- HttpOnly, expiring sessions; Argon2 password hashes; CSRF and exact origin validation; owner, administrator, and support-agent permissions.
- Workspace memberships and tenant-scoped REST, streaming, sources, retrieval, jobs, and tools. Composite database foreign keys prevent cross-tenant conversation/ticket/message references.
- PDF/TXT/Markdown uploads, bounded parsing, source pages, versioned chunks, Celery jobs, bounded retries, queued-job recovery, atomic active-version swaps, and deletion cleanup.
- Explicit LangGraph stages for context, routing, retrieval, generation, citation validation, authorized actions, verification, and persistence.
- Verified, idempotent tickets; serialized human ownership; quota enforcement; visitor-scoped history; configurable widgets and allowed embedding origins.
- Real usage records, dependency-safe errors, request IDs, retention cleanup, migrations, Docker services, locked dependencies, CI, and learning documentation.

No cloud deployment has been performed. See [verification](docs/verification.md) for exactly which checks ran and which require Docker or real-provider credentials. Do not equate SQLite/browser test-adapter results with PostgreSQL row-lock or real-worker verification.

## Development and tests

```sh
python -m venv .venv
# Activate .venv using your shell, then:
pip install -r backend/requirements.lock
cd backend
pytest -q
ruff check .
mypy app
cd ../frontend
corepack enable
corepack prepare pnpm@11.25.0 --activate
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build
```

Tests create disposable local databases. `TEST_DATABASE_URL` selects a disposable PostgreSQL database instead. **Never point it at a database you want to keep: fixtures drop all application tables.**

For browser development without Docker, use three terminals (from the repository root, with Python dependencies installed):

```sh
python scripts/local_test_server.py
pnpm --dir frontend dev
python -m http.server 3001 --bind 127.0.0.1 --directory demo-site
```

This explicitly uses SQLite, local files, inline ingestion, in-memory test rate limits, and mock models. It is a convenience test setup, not the real-worker stack. It is bound to loopback and its test adapters are prohibited outside `ENVIRONMENT=test`.

With either setup running:

```sh
cd frontend
pnpm exec playwright install chromium
pnpm test:e2e
```

An installed browser can be selected through `BROWSER_EXECUTABLE`. Run `python scripts/compose_smoke.py` only against the Docker stack to verify real-worker ingestion and cited retrieval.

## Real models

Set `MODEL_MODE=openai`, `MODEL_API_KEY`, `MODEL_BASE_URL`, `CHAT_MODEL`, and `EMBEDDING_MODEL`. The provider must support OpenAI-compatible `/embeddings` with `dimensions` and `/chat/completions` with JSON-object responses. Configure token price estimates explicitly; zero default rates mean cost is **not priced**, not that inference is free.

Changing mode, embedding model, or dimensions changes the embedding identity. Existing workspaces reject indexing/retrieval with a different identity. Restore the previous settings or create a new workspace and reupload all source documents. This version intentionally does not silently reinterpret existing vectors or offer an in-place reindex switch.

## Read next

- [Architecture](docs/architecture.md)
- [Actual request flows](docs/request-flows.md)
- [Four-day learning plan](docs/learning-plan.md) — begin Day 1 with `backend/app/models.py`.
- [Operations, deployment and recovery](docs/operations.md)
- [Verification evidence and limits](docs/verification.md)

Email invitations, password-reset delivery, billing, real order integrations, OCR, and public cloud provisioning are outside this version.
