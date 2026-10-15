# Verification record

The latest real-infrastructure verification is the [successful GitHub Actions run for commit `8a5be4e`](https://github.com/MutteUllah/supportdesk-ai/actions/runs/38733881701) on 15 October 2026: 34 PostgreSQL tests, the real worker/storage smoke, and browser acceptance passed with mock models. Details are recorded at the end of this document.

The original 12 October 2026 Windows results below are preserved as historical evidence. They used Python 3.10.10, Node 24.19.0, and Microsoft Edge through Playwright; Docker was unavailable on that Windows machine.

## Passed checks

| Check | Command actually run | Result |
|---|---|---|
| Backend acceptance | `python -m pytest -q backend` from repository root | **27 passed, 2 skipped** in the final run |
| Python types | `python -m mypy --config-file backend/pyproject.toml backend/app` | No issues in 13 application files |
| Python lint | `python -m ruff check backend scripts` | Passed |
| Python format | `python -m ruff format --check backend scripts` | Passed; newly added packaging helper was formatted separately |
| TypeScript | `node node_modules/typescript/bin/tsc --noEmit` in frontend | Passed; production build also completed TypeScript validation |
| Frontend lint | `node node_modules/eslint/bin/eslint.js .` in frontend | Passed |
| Frontend/widget formatting | `node node_modules/prettier/bin/prettier.cjs --check app scripts tests '*.ts' '*.mjs' '*.json' '../widget/*.js' '../widget/*.html' '../demo-site/*.html'` in frontend (equivalent Windows paths used) | All checked files formatted |
| Production frontend | `node node_modules/next/dist/bin/next build` | Compiled and prerendered successfully |
| Production startup | `node scripts/start.mjs` in frontend | Standalone server started successfully on port 3000 |
| Browser acceptance | `node node_modules/@playwright/test/cli.js test`, with `BROWSER_EXECUTABLE` set to installed Edge | **1 complete end-to-end scenario passed**, final production-build run: 13.6 seconds |
| SQLite migrations | `python -m alembic upgrade head`, `check`, `downgrade base`, `upgrade head` | Passed; no model drift detected |
| PostgreSQL SQL generation | `python -m alembic upgrade head --sql` with PostgreSQL dialect URL | Compiled successfully; SQL saved in `schema-postgresql.sql`; no database connection made |
| Compose structure | Parsed `docker-compose.yml` with PyYAML and checked service/shared settings | Ten services parsed; this is not a Docker runtime validation |
| Widget JavaScript syntax | `node --check widget/app.js` | Passed |
| Dependency resolution | pip-compile and pnpm install/add | Python and frontend lockfiles generated; frontend native resolver's optional build script is explicitly disabled in `pnpm-workspace.yaml` |

All Python commands used a workspace virtual environment. Node commands used the installed local packages directly because npm was not present on PATH; the documented pnpm scripts invoke those same tools.

## Backend coverage

`backend/tests/test_acceptance.py` and `test_failures.py` cover:

- Absent/expired authentication, password login/logout, CSRF, role restrictions, cross-workspace documents/conversations/tickets/sources/streams, and composite database constraints.
- Unsupported/empty/oversized uploads, real text-PDF extraction and upload, scanned-PDF rejection, ingestion idempotency, failed replacement preserving the active version, successful replacement excluding superseded evidence, deletion revoking sources/search, and storage failure reporting.
- Different policies in two workspaces, unsupported-question fallback, real retrieved citation identifiers, injected document instructions not executing tools, invalid generated citations rejected, safe provider errors, ticket consent/idempotency, explicit ticket-outcome verification, and bot suppression during human control.
- Workspace quotas with replay handling, Redis outage fail-closed behavior, rate limits, visitor separation/expiry, iframe restrictions, and reproducible two-business seeding.

The two skipped tests in `test_postgres_concurrency.py` are concurrent ticket retries and concurrent agent claims. SQLite does not implement PostgreSQL row locks, so pretending these passed would be misleading.

## Browser coverage

`frontend/tests/acceptance.spec.ts` ran against the actual production Next.js standalone frontend, actual FastAPI HTTP endpoints, a separate website on port 3001, and the embedded iframe. It verified:

1. Registration and workspace creation.
2. Document upload and searchable status.
3. Chat answer and a source-view dialog.
4. Explicit ticket creation and ticket status update.
5. Permitted origin settings and the external embed.
6. Visitor chat and conversation continuity after refresh.
7. Human request, inbox claim, agent reply delivered to the widget, and return to bot.
8. Logout, login, retained workspace access, desktop/mobile screenshots, and no horizontal page overflow at 390 px.

The backend used **explicit test adapters**: SQLite, local files, inline Celery execution, in-memory test rate limits, and deterministic mock models. This proves application/UI integration in that configuration. It does **not** prove actual Redis delivery, MinIO access, PostgreSQL locking, or real LLM inference.

Screenshots are retained at `docs/screenshots/dashboard-desktop.png` and `docs/screenshots/dashboard-mobile.png`. The development screenshots were visually inspected; the final production run regenerated them without development tooling.

## Defects found and fixed

- Equal timestamps could reorder a customer/assistant message pair. Response timestamps now follow the customer message deterministically.
- The password's helper text made its accessible name ambiguous. The input has an explicit accessible label.
- The iframe sandbox blocked form submission. The loader grants `allow-forms`, alongside its required script/same-origin capabilities.
- Widget actions could be clicked before visitor initialization. Controls remain disabled until the session is ready.
- Human-message text lacked a distinct element, and widget scroll position was lost on refresh. Message content now has its own text span and polling preserves scroll position.
- Logout retained registration-screen state. It now returns to login.
- A claim response could clear a newly typed agent draft. Draft clearing now occurs only for submitted replies; input is disabled while an action is pending.
- Standalone Next.js output needs static assets copied before local startup. The cross-platform `frontend/scripts/start.mjs` performs that copy and starts the generated server.
- Citation views originally truncated evidence independently of generation. Generation now receives exactly the bounded excerpt stored for source viewing.

## Checks unavailable during the original 12 October verification

**Docker CLI/daemon was unavailable on the original Windows machine.** Docker image builds and the full Compose smoke were subsequently verified in GitHub Actions on 15 October, as recorded below. To reproduce on a Docker-capable machine:

```sh
cp .env.example .env
docker compose up --build -d --wait
python scripts/compose_smoke.py
docker compose exec postgres createdb -U supportdesk acceptance
# Set TEST_DATABASE_URL to the disposable acceptance database, then:
cd backend
pytest -q
cd ../frontend
pnpm test:e2e
```

Example disposable test URL: `postgresql+psycopg://supportdesk:supportdesk-local-change-me@localhost:5432/acceptance`. Test fixtures drop application tables: do not use your application database. No remote repository was configured for the original 12 October check; the CI workflow has since passed the real Compose smoke, PostgreSQL test suite, and browser scenario.

**No real-provider credentials were supplied.** No paid inference was run. With a configured key and `MODEL_MODE=openai`, run `python scripts/real_provider_smoke.py` as an explicit small provider check, then create a fresh workspace and test your own policies through the full app. Evaluate grounding and prompt-injection behavior with the selected real model separately.

**No cloud deployment was performed.** Backup/restore commands and production configuration are documented, but infrastructure failover, live PostgreSQL migration/restore, load testing, and external HTTPS/proxy deployment still need validation in the target environment.

The original local record did not validate real infrastructure. The later remote run below closes the Compose, worker/storage, PostgreSQL concurrency, and browser-integration gaps; cloud deployment and real-model evaluation remain outstanding.

## Prepublication recheck — 15 October 2026

The existing checks were rerun on Windows with the project's installed Python virtual environment, Node 24.19.0, and Microsoft Edge. The application code was unchanged for this publication preparation.

| Check | Command or method | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` from `backend` | **27 passed, 2 skipped in 7.91 seconds**; PostgreSQL concurrency tests still require PostgreSQL |
| Python types | `python -m mypy --config-file backend/pyproject.toml backend/app` | Passed; 13 source files |
| Python lint and format | `ruff check backend scripts`; `ruff format --check backend scripts` | Passed; 24 Python files already formatted |
| Frontend lint and types | `pnpm lint`; `pnpm typecheck` from `frontend` | Passed |
| Production frontend | `pnpm build` from `frontend` | Passed; compiled, typechecked, and prerendered with Next.js 16.4.0 |
| Browser acceptance | `pnpm test:e2e` from `frontend`, with `BROWSER_EXECUTABLE` set to installed Edge | **1 passed in 11.9 seconds** against the production frontend, local mock backend, and demo website |
| Widget syntax | `node --check widget/app.js`; `node --check widget/loader.js` | Passed |
| Configuration syntax | PyYAML parsing of Compose, CI workflow, and both GitHub issue forms | Passed; 10 Compose services; issue forms contain required metadata and bodies |
| Source audit | Common credential signatures and private-key headers checked across all 68 initially tracked files and the single existing commit | No matches; no tracked environment-secret files, runtime databases, dependency directories, build output, or private-key files |
| Ignore rules | `git check-ignore` with 11 representative paths | Environment variants, databases and WAL files, logs, build output, and test artifacts are ignored; `.env.example` remains publishable |
| Whitespace | `git diff --check` | Passed |

Git and Docker ignore rules were expanded to cover environment-file variants, SQLite sidecar files, logs, virtual environments, and browser-test artifacts. The credential scan checks recognizable signatures; it is not a guarantee that every possible secret format can be detected. Example local-development credentials remain deliberately documented in `.env.example` and Compose.

This Windows browser scenario again used SQLite, local file storage, inline jobs, in-memory test rate limits, and mock models. Its temporary loopback servers were stopped after verification. Docker and real PostgreSQL/Redis/MinIO integration were not run in this Windows recheck; they were validated subsequently in remote CI below. Cloud deployment and paid model inference remain unverified.

The sandbox initially denied Node's canonical-path lookup. Frontend verification was rerun successfully with access to the existing workspace and dependencies; the results above reflect that completed run.

## Remote infrastructure verification — 15 October 2026

Both jobs passed in [GitHub Actions run 38733881701](https://github.com/MutteUllah/supportdesk-ai/actions/runs/38733881701) for code revision [`8a5be4e`](https://github.com/MutteUllah/supportdesk-ai/commit/8a5be4e986c7c264c9a7e5b0d33938478c81807e). The workflow used an Ubuntu runner, Python 3.10, Node 24, and pnpm 11.25.0.

| Check | Executed evidence | Result |
|---|---|---|
| Python/frontend checks | Locked installs, Ruff lint/format, mypy, pytest, ESLint, TypeScript, production Next.js build | Passed; mypy checked 14 source files; SQLite tests: **32 passed, 2 skipped in 5.00 seconds** |
| Container build and startup | `docker compose up --build -d --wait --wait-timeout 240` | All ten services built/started according to their readiness/dependency conditions, including migrations, storage initialization, API, worker, and beat |
| Real ingestion and cited answer | `python scripts/compose_smoke.py` against the Compose API | Passed: actual Celery worker, MinIO object storage, Redis, and PostgreSQL/pgvector produced a searchable document and a cited answer |
| PostgreSQL acceptance | Disposable `acceptance` database with `TEST_DATABASE_URL`, then `pytest -q` in `backend` | **34 passed in 7.90 seconds**, including concurrent ticket retries and exclusive agent claims; no PostgreSQL skips |
| Browser acceptance | Playwright Chromium against the production frontend and Compose backend/demo website | **1 passed in 16.7 seconds**; registration, knowledge ingestion, source dialog, tickets, widget continuity, human handoff, login, and mobile overflow assertion |

The first remote attempt exposed unavailable upstream MinIO Docker Hub images. The repair builds the same pinned MinIO server release from official Go source and initializes its bucket using the backend's existing boto3 client. Five focused initializer tests cover an existing bucket, missing bucket, forbidden access, concurrent creation, and a conflicting bucket. No workflow checks were disabled to obtain the successful result.

The Compose application used **mock embedding and answer generation**, with real database/storage/broker/worker services. The PostgreSQL pytest fixtures additionally use inline jobs, local storage, and in-memory test rate limits to isolate test cases; the independent Compose smoke and browser scenario exercise the actual services. These results do not establish paid-provider connectivity, real-model answer quality, production performance, backups/failover, or cloud deployment.
