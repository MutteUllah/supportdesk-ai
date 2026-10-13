# Four days to understand and rebuild SupportDesk AI

Keep the working application as your reference. Initialize a Git repository if needed, commit the working baseline, and use `git switch -c learning/day-1` for exercises. Use a separate disposable database and ports for experimental copies. Do not change the running baseline while learning.

## Day 1 — Identity, data, and authorization

**Read in order:** `backend/app/models.py` (start here), `backend/app/db.py`, `backend/migrations/versions/0001_initial.py`, `backend/app/config.py`, `backend/app/schemas.py`, `backend/app/security.py`, the auth/workspace/member handlers in `backend/app/main.py`, then `backend/tests/test_acceptance.py`.

**Understand:** SQLAlchemy mapped columns, foreign keys versus authorization, composite tenant references, Alembic migrations, Argon2, random token hashing, HttpOnly cookies, CSRF, session expiry, and role checks. Recognize why a UUID is not an access-control mechanism.

**Trace one complete request:** log in from the dashboard. Follow `auth → /auth/login → auth_limit → verify_password → set_session`, inspect the cookie flags in browser developer tools, then trace `/workspaces` through `authenticated` and the membership join.

**Exercises on your learning branch:** add a workspace description field via a new migration; return it through the API and settings form. Add a test that a support agent cannot modify it. Build a small endpoint that returns the caller's role and prove that another workspace yields 404. Do not replace secure session cookies with localStorage tokens.

```sh
cd backend
pytest -q -k 'auth or roles or login or constraint'
alembic current
alembic revision --autogenerate -m 'workspace description'
# Review the generated file before applying to your disposable database.
alembic upgrade head
```

**Observable results:** expired or absent cookies receive 401; absent CSRF receives 403; foreign workspace IDs receive 404; valid login returns a CSRF value and a separate HttpOnly cookie.

**Answer afterward:** Why hash a high-entropy session token? Why does SameSite not replace CSRF? Which checks prevent cross-tenant reads? Which constraints prevent cross-tenant writes? What is the difference between authentication and membership?

## Day 2 — Durable knowledge ingestion

**Read in order:** document tables in `models.py`, `storage.py`, upload handlers in `main.py`, `ingestion.py`, embedding functions in `provider.py`, retrieval in `chat.py`, `docker-compose.yml`, ingestion tests in `test_acceptance.py`.

**Understand:** S3 object keys, durable job intents, broker/worker separation, text-based PDF parsing, page-preserving chunks, overlap, embedding identity, pgvector distance, idempotent insertion, document locks, version switching, tombstones, and eventual cleanup.

**Trace one request:** upload a Markdown policy. Follow file validation → queued version → S3 put → Redis dispatch → Celery `ingest` → `process_version` → chunks → active pointer. Watch the Documents page while reading worker logs.

**Exercises:** change chunk size on an empty experimental workspace; inspect the resulting chunk count. Introduce a controlled embedding failure on a replacement and show that the previous version still answers. Invoke the same version job twice and verify no duplicate chunk ordinals. Add a parser unit test for a multi-page text PDF.

```sh
docker compose logs -f worker
docker compose exec api python -m app.seed
python scripts/compose_smoke.py
cd backend
pytest -q -k 'ingestion or upload or delete or embedding'
```

**Observable results:** queued → processing → ready; invalid content becomes failed with a safe error; old versions remain active on failure; a successful replacement changes citations to the new version; deletion removes retrieval immediately.

**Answer afterward:** What happens if the API commits but Redis is down? Why keep old versions until the replacement is ready? How do you prevent an old job finishing late from replacing newer knowledge? Why must model/dimension changes require reindexing?

## Day 3 — Conversation workflow and product integration

**Read in order:** `chat.py` from `State` through `run_chat`, `provider.py`, streaming/source/ticket/visitor routes in `main.py`, `frontend/app/page.tsx`, `widget/loader.js`, `widget/app.js`, `frontend/tests/acceptance.spec.ts`.

**Understand:** graph state versus durable history, bounded context, grounded answers, evidence identifiers, explicit consent, verified side effects, idempotency keys, SSE frames, partial transport failures, iframe origins, visitor bearers, and safe text rendering.

**Trace one request:** ask “How long does shipping take?” through the demo widget. Trace bearer authorization, tenant-filtered retrieval, validated source IDs, message commit, SSE, message polling, and source-view authorization. Then create one ticket and retry its exact request key through the API.

**Exercises:** add a graph stage recording whether an answer used evidence (without logging question text). Add a UI filter for open tickets. Add a test that a fabricated citation is rejected. Introduce an SSE disconnect and fetch the saved history before retrying. Keep tool authorization outside generated model output.

```sh
cd backend
pytest -q -k 'evidence or citation or ticket or widget or provider'
cd ../frontend
pnpm typecheck
pnpm test:e2e
```

**Observable results:** two businesses answer different policies; unknown questions offer clarification/support; source views reveal only cited excerpts; a repeated ticket key returns the same reference; widget history survives refresh while its visitor session is valid.

**Answer afterward:** Why validate citations before streaming? Can an injected document invoke a tool? Why can a public workspace ID not retrieve a private conversation? What does `done` mean? How does a real provider differ from the mock?

## Day 4 — Failure handling, concurrency, and operations

**Read in order:** `test_acceptance.py`, `test_postgres_concurrency.py`, `security.py::rate_limit`, `chat.py::run_chat`, `main.py::human_action`, `ingestion.py::maintenance`, Dockerfiles, `docker-compose.yml`, `.github/workflows/ci.yml`, `docs/operations.md`, and `docs/verification.md`.

**Understand:** transaction locks, concurrent quota accounting, bounded retries, uncertain action outcomes, fail-closed rate limits, request IDs, retention, migrations, persistent volumes, backup consistency, and differences between test adapters and real dependencies.

**Trace one request:** request human support in the widget, claim from the inbox, send a human reply, and return to the bot. Follow state/revision changes and the polling response. Attempt a second simultaneous claim with another account.

**Exercises:** run PostgreSQL concurrency tests in a disposable database. Stop Redis and observe 503 for rate-limited requests; restart it and observe queued-job recovery. Stop MinIO during replacement and verify old knowledge still works. Perform a backup/restore drill into a new environment. Add a test for a discovered failure, then implement its fix.

```sh
docker compose up --build -d --wait
python scripts/compose_smoke.py
docker compose exec postgres createdb -U supportdesk learning_tests
# Set TEST_DATABASE_URL to learning_tests only, never your working database.
cd backend
pytest -q
ruff check .
mypy app
cd ../frontend
pnpm lint && pnpm typecheck && pnpm build && pnpm test:e2e
```

**Observable results:** only one concurrent claim succeeds; repeated ticket actions yield one row; a human-owned conversation never generates a new bot answer; missing infrastructure produces safe errors; restored rows still resolve their stored objects.

**Answer afterward:** What is and is not proven by SQLite tests? Why must consequential actions use durable keys? Which operation holds the workspace lock and what is its throughput cost? How would you scale it safely? Which secrets and customer records are in backups? Which production checks remain before launch?
