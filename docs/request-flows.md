# Request flows through actual code

## Login

1. `frontend/app/page.tsx::auth` posts credentials to `/auth/login` with cookies enabled.
2. `main.py::auth_limit` validates the dashboard Origin and increments an atomic Redis authentication limit. Forwarded client IP headers are not trusted by application code.
3. `main.py::login` looks up normalized email and calls `security.py::verify_password` (Argon2). A dummy hash check handles unknown accounts.
4. `main.py::set_session` saves the hash of a random opaque token with an expiry and independent CSRF secret. It returns the user and CSRF token and sets the raw session token only in an HttpOnly cookie.
5. Subsequent write requests send `X-CSRF-Token`; `security.py::authenticated` checks token hash, expiration, exact Origin, and CSRF. `member` enforces the requested workspace and role.

`/auth/logout` removes the server session. `/auth/me` recovers CSRF after refresh. Production requires HTTPS and Secure cookies.

## Document ingestion

1. Dashboard `upload` sends multipart data to `main.py::upload` or `replace_document`.
2. Membership is checked for owner/administrator. `limits.py::BodyLimitMiddleware` caps request bodies before multipart parsing; `upload_document` checks extension, file length, and PDF magic.
3. A document/version with a unique object key is committed as queued, then `storage.py::put` writes the original. Storage failures leave actionable failed metadata. This sequencing prevents untracked uploaded objects after a process crash.
4. `ingestion.py::dispatch` sends `ingest(workspace_id, version_id)` through Redis. A broker failure leaves the durable queued record for `maintenance` to redispatch.
5. `ingest` records processing and an attempt count. `process_version` checks both IDs, locks the document, calls `extract`, `split`, and `provider.embeddings` in batches.
6. It replaces that version's chunks within one transaction and advances `active_version_id` only if newer. A transient failure is retried with backoff, at most four attempts; invalid documents fail without retry.
7. The dashboard polls status. Deletion immediately tombstones; `maintenance` reliably retries object/chunk cleanup.

## Chat and citations

1. Playground `send` or widget `send` posts `{text, request_key, action:"chat"}`.
2. `main.py::chat` checks membership; `visitor_chat` checks the visitor-scoped conversation. `stream_reply` sends a status frame.
3. `chat.py::run_chat` locks workspace then conversation, checks replay, and reserves daily quota in the same transaction.
4. Graph nodes run: `load_context → route_request → retrieve → generate → validate_citations → execute_tool → verify_tool → save_result`.
5. `retrieve` joins workspace-filtered chunks, versions, and nondeleted documents whose active version matches. OpenAI mode uses pgvector cosine distance; mock mode uses deterministic hashed lexical vectors plus word overlap. Embedding identity must match.
6. `generate` returns a supported answer or a no-evidence response. `validate_citations` rejects IDs outside retrieved evidence. No citations with retrieved sources causes a fallback rather than an unsupported policy answer.
7. `save_result` stores messages, short citation excerpts, model identity, latency, token counts if available, and estimated cost. Commit succeeds before text is emitted.
8. Clicking a source calls `source_content`; visitors must own the citation's conversation. Deleted sources return unavailable. Original document download is a separate membership-only endpoint.

### SSE contract

POST with fetch streaming, `Content-Type: text/event-stream`. Each frame is `event: NAME\ndata: JSON\n\n`.

| Event | Payload | Meaning |
|---|---|---|
| `status` | `{state:"working",request_key}` | Request accepted for processing |
| `delta` | `{text}` | Slice of validated, committed response |
| `done` | `{message_id,request_key}` | Fetch message history for canonical citations |
| `error` | `{detail,status}` | No successful completion; show actionable message |
| `interrupted` | `{detail}` | Ownership/session changed; refresh canonical history |

The client must require `done`, not infer success from transport close. A disconnected client may have a committed response. Retry the unchanged logical action with the **same request key** to retrieve it without repeating ticket creation or quota consumption. The UI retains the key on failures. A fresh message receives a new key. Full page reload during an unacknowledged action requires fetching history before resubmitting; the in-flight key is not persisted across reload.

Provider generation is bounded by a configurable per-attempt timeout and at most three read-only API attempts. Document workers have Celery soft/hard time limits. No model response is emitted before validation, so a provider failure cannot expose partial unverified output.

## Ticket creation and verification

The ticket dialog collects subject, description, and optional email. Submission sets `action:"ticket"`, `consent:true`, and a request key. `route_request` refuses missing subject/consent. `execute_tool` looks up an existing ticket by conversation/action key or inserts it with a tool-execution record. `verify_tool` queries that ticket in the authorized conversation and marks the execution verified. Only after `save_result` and transaction commit does SSE report its actual UUID reference. The language model cannot request or authorize this path.

## Human takeover

`action:"handoff"` transitions bot → pending-human. It explicitly states no agent has joined. The inbox lists non-bot conversations. `main.py::human_action` locks the conversation. `claim` rejects an already-owned conversation with 409; `reply` and `release` require the current agent. Human messages persist as `role:"agent"`. The widget's 3-second `refresh` poll loads them. `release` restores bot state and increments the revision. Removing a workspace member returns their owned conversations to the pending queue.

## Embedded visitor authentication

`widget/loader.js` uses `data-workspace` and creates a sandboxed iframe under the API origin. The exact embedding origin is carried in its URL fragment. The server sets `frame-ancestors` from validated workspace settings. `widget/app.js::start` fetches public display configuration and posts the embedding origin to `/public/{public_id}/session`.

The API rate-limits session creation, validates the permitted origin, then creates a short-lived hashed-token visitor session and one conversation. The raw bearer is only returned at creation. Widget requests send it through Authorization. `security.py::visitor` checks hash/expiry and rate-limits requests; every conversation/source access verifies the visitor ID. The bearer can only access that visitor's workspace and conversation.

The iframe stores this scoped token under a workspace+embedding-origin key when the browser permits third-party storage. It is unrelated to dashboard authentication. Expiry begins a new session; anonymous recovery of expired sessions is intentionally unavailable. Browsers blocking iframe storage support the current page session but cannot guarantee refresh continuity.
