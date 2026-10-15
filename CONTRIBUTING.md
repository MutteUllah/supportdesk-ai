# Contributing to SupportDesk AI

Thanks for helping improve SupportDesk AI. Read the [README](README.md) for setup and the [architecture guide](docs/architecture.md) before changing behavior across the API, dashboard, worker, or widget.

## Local workflow

1. Create a focused branch from the current default branch.
2. Copy `.env.example` to `.env` and use development-only credentials. Keep secrets, uploaded documents, databases, backups, and generated build artifacts out of commits.
3. Install the locked Python and frontend dependencies using the [development instructions](README.md#development).
4. Reproduce the behavior you intend to change. Use Compose for worker, Redis, object-storage, PostgreSQL, or concurrency changes; the local test server uses explicit test adapters.
5. Make the smallest coherent change, update relevant documentation, and run the checks below that cover it.

Do not run tests against an application database. The backend fixtures drop application tables. Use a new disposable database when setting `TEST_DATABASE_URL`.

## Quality checks

From the repository root, with the Python virtual environment activated:

```sh
python -m pytest -q backend
python -m ruff check backend scripts
python -m ruff format --check backend scripts
python -m mypy --config-file backend/pyproject.toml backend/app
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

Run `pnpm --dir frontend test:e2e` with the API, dashboard, and separate demo website running when changing a user journey. Install Playwright Chromium first, or set `BROWSER_EXECUTABLE` to a compatible installed browser. The [verification guide](docs/verification.md) explains the full setup and real-infrastructure checks.

For backend behavior changes, add regression coverage for the relevant failure or permission boundary. Documentation-only changes can be checked by reviewing instructions, links, and claims against the current code. Record what actually ran and clearly distinguish skipped or unavailable checks.

## Implementation conventions

- Preserve workspace and visitor scoping on reads, writes, retrieval, sources, and background jobs. An unguessable ID is not authorization.
- Keep model-generated text separate from permission to perform actions. Ticket creation and handoff require explicit structured customer actions.
- Preserve logical request keys and transactional verification when changing chat or ticket retries.
- Treat document text, user text, and provider responses as untrusted. Render them as text unless a separately reviewed safe renderer is introduced.
- Keep credentials on the backend. `NEXT_PUBLIC_` variables are public build-time configuration.
- Add a new Alembic revision for a schema change. Do not rewrite a migration that may already have been applied. Test against a disposable PostgreSQL database.
- Keep the dependency lockfiles in sync when dependencies change. Do not include `node_modules`, virtual environments, or build outputs in a pull request.
- Follow applicable `AGENTS.md` instructions. The frontend contains version-specific Next.js guidance for coding agents.

## Pull requests

Explain the problem and resulting behavior for a reviewer who has not seen the discussion. Include:

- The concrete trigger and before/after behavior.
- Relevant tests and their actual results, including skips or limitations.
- Screenshots for visible UI changes, using fictional data.
- Migration, configuration, deployment, or compatibility steps when applicable.
- Any remaining operational limits that affect the change.

Keep unrelated cleanup separate. Do not claim real-provider, PostgreSQL locking, Docker, or cloud verification based on mock/SQLite checks.

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md). Public issues and pull requests should omit secrets, private customer data, and exploitable details of unresolved vulnerabilities.
