# Operations

## Configuration and startup

Copy `.env.example` to `.env`, keep it outside version control, configure a unique demo password if seeding, and run `docker compose up --build -d --wait`. The `migrate` service applies Alembic before API startup; `storage-init` creates the private MinIO bucket; API readiness gates worker/frontend startup. Named volumes persist PostgreSQL, Redis, and MinIO data.

`docker compose exec api python -m app.seed` creates two fictional businesses and queues their policies. It refuses `ENVIRONMENT=production`. Repeating it does not duplicate workspaces or documents. Changing `DEMO_PASSWORD` does not overwrite an existing user's password; create a new development database if you need fresh demo accounts.

Use `docker compose down` to stop while keeping data. Do not add `-v` unless you deliberately intend to erase local volumes.

## Migrations

```sh
docker compose run --rm migrate
docker compose exec api alembic current
docker compose exec api alembic check
```

For a new schema change, generate and review a new Alembic revision against a development PostgreSQL database. The committed `0001_initial.py` contains frozen operations. `scripts/generate_initial_migration.py` is a build-time reference helper; **do not regenerate migration 0001 once a deployment uses it**. Back up first, test migrations against a restored copy, and plan rollbacks at the application/data level. The app does not auto-create tables in production.

## Production deployment

This repository provides deployment configuration; it does not provision public infrastructure or purchase services. Before release, run the actual Compose smoke and PostgreSQL concurrency tests documented in verification.md.

1. Deploy the API, Celery worker, and exactly one Celery beat instance from the same backend image. Run the migration once as a release task. Use managed PostgreSQL with the `vector` extension, Redis, and S3-compatible storage or hardened equivalents.
2. Set `ENVIRONMENT=production`. Choose HTTPS dashboard/API origins on the same site (for example `app.example.com` and `api.example.com`) so SameSite=Lax cookies work. Separate unrelated domains need an explicitly reviewed cookie/CSRF design; they are not the default topology.
3. Build the frontend with its real `NEXT_PUBLIC_API_URL`. This is a public build-time value. Never put a model API key in a `NEXT_PUBLIC_` variable.
4. Configure TLS at a trusted reverse proxy. Disable buffering for SSE, allow the provider timeout/retry budget, and cap request bodies at 11 MB. The application also bounds request bodies. Only trust forwarded IPs from your configured proxy; configure Uvicorn `--forwarded-allow-ips` to that proxy's exact address, not arbitrary clients.
5. Keep database, Redis, and object-storage administration private. Compose's host bindings are loopback development bindings, not a public production routing configuration. Use least-privilege bucket credentials and do not expose the MinIO console publicly.
6. Configure secrets through your deployment secret manager, change all local storage/database credentials, and use restricted CORS plus explicit workspace embedding origins. HTTPS origins and nonlocal storage credentials are validated at startup in production.
7. Choose real model configuration and pricing, create a fresh workspace, upload policies, and conduct a small separately recorded real-provider smoke test. Confirm source correctness, unsupported-question behavior, and injection resilience before customer use.
8. Add monitoring for API error/latency, queued-job age, failed versions, worker health, Redis availability, database connections/locks, and object storage errors. `/health` checks the process; `/ready` checks database, Redis, and the bucket. `/ready` does not prove that a worker is consuming jobs; worker health and the real ingestion smoke are separate checks.

Production is not automatically seeded. Email delivery/reset flows, billing, public cloud provisioning, order-system integrations, OCR, malware scanning, and high-availability deployment automation are not provided.

## Provider and retrieval settings

Mock mode is labeled in the dashboard, widget, and answers. It hashes words into deterministic vectors and extracts source text. It cannot reason like an LLM and should only be used for tests/demonstration. Mock retrieval uses positive lexical overlap, whereas real-provider retrieval uses the configured cosine-distance threshold. Calibrate `RETRIEVAL_MAX_DISTANCE` against your own policies; no threshold guarantees semantic entailment.

`MODEL_MODE=openai` uses bounded, retried HTTP calls to OpenAI-compatible endpoints. The service must accept embedding dimensions and JSON-object chat responses. Only read-only provider calls are retried automatically; tickets are protected by durable logical action keys. Default provider timeout is 30 seconds per attempt, with three attempts and short backoff. Do not put API credentials in browser bundles.

Changing embedding mode/model/dimensions requires a new workspace/reupload or restoring the original configuration. Automated in-place reindexing is intentionally absent. Source backups are essential for reindexing. The retrieval implementation performs exact tenant-filtered vector searches; use corpus/latency measurements before adding approximate indexes.

Token counts come from provider responses when supplied. Mock counts are zero. `INPUT_COST_PER_MILLION` and `OUTPUT_COST_PER_MILLION` default to zero (unpriced); estimated costs are not billing records.

## Failure behavior

| Failure | Behavior and recovery |
|---|---|
| Redis down | Auth/public chat limits fail closed with 503. Upload records can remain queued; beat recovers dispatch after Redis returns. |
| Worker down | Uploads remain queued. Inspect worker health/logs; restart it. Stale queued/processing jobs are reconsidered after six minutes. |
| Storage write failure | Version becomes failed with an actionable error. Working versions remain searchable. Upload a replacement after recovery. |
| Storage cleanup failure | Tombstone continues to revoke retrieval/sources. Cleanup is retried by maintenance. |
| Model timeout/invalid response | Safe SSE error, no unverified answer or tool success. Transaction rolls back; retry with the same logical request key. |
| Interrupted response | Require `done`; fetch canonical history before resubmitting. The server may already have committed the response. |
| Session expired | Dashboard gets 401; log in again. Expired anonymous visitor sessions are not recoverable. Start a new visitor session. |
| Quota reached | 429 with a workspace daily-limit message. UTC date rollover resets accounting under a workspace lock. |
| Database unavailable | Readiness fails; operations cannot safely continue. Restore database connectivity before retrying. |

Logs intentionally contain request ID, method, status, and latency, without complete paths, conversations, documents, credentials, or cookies. Client errors include request IDs; validation errors omit submitted values. Uvicorn access logs are disabled in Docker. If adding exception logging, keep provider bodies and request payloads redacted.

## Backup and restore

Make PostgreSQL and object backups as a matched set. For a simple consistent maintenance-window backup, stop API, worker, and beat writers; leave PostgreSQL/MinIO running. Never back up only the database and assume uploaded objects are recoverable.

```sh
docker compose stop api worker beat
mkdir -p backups
# POSIX shell binary-safe output:
docker compose exec -T postgres pg_dump -U supportdesk -Fc supportdesk > backups/supportdesk.dump
# On Windows, avoid legacy PowerShell binary redirection: write the dump in the container,
# then use docker compose cp postgres:/tmp/supportdesk.dump backups/supportdesk.dump.
```

Use the official MinIO `mc` client configured with the deployment's credentials through an environment/secret mechanism. `mc mirror local/supportdesk backups/objects` copies the private bucket. Encrypt and restrict the backups because they contain user emails, document content, password hashes, session hashes, conversations, and ticket details. Restart writers after the snapshot: `docker compose start api worker beat`.

Restore into a **new disposable environment first**. Create the target bucket, mirror the saved objects back preserving exact keys, create an empty database, and use `pg_restore --no-owner -U supportdesk -d supportdesk` with the dump. Then apply pending migrations, invalidate sessions if this is disaster recovery, and run a cited-answer smoke against known documents. Never run a destructive restore over the sole surviving production copy.

Redis is not the source of truth for jobs: queued database rows permit re-dispatch. Redis AOF persists local broker state, but restoration must not duplicate consequential actions; document jobs are idempotent and ticket action keys are relational.

## Retention and deletion

`RETENTION_DAYS` defaults to 90. Minute-based maintenance deletes conversations older than that age **from creation**, cascading messages, citations, tickets, and tool executions, and deletes expired dashboard sessions. Visitor history remains until retention even when its token has expired. Usage events remain for reporting; add a separate aggregation/retention policy before a high-volume deployment.

Dashboard conversation deletion is available to administrators/owners. Document deletion immediately revokes sources and search access. Worker maintenance later removes originals and chunks. Superseded versions are not retrieved but remain retained so historical citations are usable until document deletion. Account export/deletion workflows and granular legal-retention controls are future work.

## Known operating limits

- Chat holds a workspace lock during model generation. This prevents quota races but serializes that workspace's concurrent requests; it is appropriate for this understandable first version, not a high-throughput architecture.
- SSE streams committed, validated text, not raw model tokens. No resumable SSE cursor is exposed; use persisted message history on interruption.
- List endpoints currently cap conversations/tickets at 200; pagination/search beyond that is future work.
- HTTP model configuration is compatible only with providers implementing the requested endpoints and response formats. No real-provider run is claimed without credentials and recorded evidence.
- Embedding-origin checks are not authentication, and visitors can obtain additional anonymous sessions. IP/visitor limits and workspace quotas bound abuse, but production may require gateway bot protection and user verification.
- Third-party storage restrictions can prevent anonymous widget continuity across refreshes. The current page still works; token expiry requires a new session.
- Literal text rendering avoids HTML injection; rich Markdown rendering is not implemented.
- Stored citation identifiers are validated, but this is not a proof of every generated sentence's entailment. Evaluate real-model outputs with business-specific test questions.
