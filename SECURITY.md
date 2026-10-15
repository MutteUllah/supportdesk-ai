# Security policy

SupportDesk AI is an application implementation with documented local verification and deployment requirements. This repository does not claim an independent security audit. The [verification record](docs/verification.md) states the scope and limitations of executed checks.

## Report a vulnerability

Use the repository's **Security → Advisories → Report a vulnerability** action if private vulnerability reporting is enabled. Otherwise, use a private contact method published by the repository owner before sharing sensitive details. This repository does not designate a security email address or promise a response deadline.

Do not publish credentials, customer data, or exploitable details in a public issue. A useful private report includes:

- The affected commit and component.
- Reproduction steps in a local environment with fictional data.
- Expected and actual behavior, impact, and relevant permission boundaries.
- A minimal request or proof of concept with tokens, passwords, and personal data removed.

Only test systems and data you are authorized to access. Prefer a disposable local installation and separate workspaces when demonstrating isolation issues.

## Security boundaries in this implementation

- Dashboard authentication uses expiring HttpOnly cookies, hashed opaque session tokens, Argon2 password hashes, and CSRF/origin checks.
- Workspace API access requires membership and appropriate roles. Visitor access is scoped to a visitor session and its conversation.
- A public workspace ID identifies an embed; it does not grant dashboard access. Origin restrictions are browser controls, not proof of caller identity for arbitrary HTTP clients.
- Citation identifiers must belong to retrieved evidence. Model text cannot authorize a ticket or human handoff.
- Upload parsing is bounded and limited to supported document types. OCR and malware scanning are not included.
- Provider credentials remain server-side. Real-provider operation sends questions, recent chat context, and retrieved document excerpts to the configured provider; document ingestion sends extracted chunks for embedding.

These controls do not substitute for a deployment review or business-specific evaluation of generated answers. See [Architecture](docs/architecture.md) for trust boundaries and [Operations](docs/operations.md) for production configuration.

## Deployment and maintenance

Use HTTPS and nondefault credentials, keep database/Redis/storage administration private, restrict permitted origins, and configure backups and retention for the data you collect. Preserve the tenant constraints and action-verification boundaries when modifying the application.

Never commit `.env`, API keys, session tokens, private documents, database dumps, or production logs. If a credential is exposed, revoke or rotate it with its provider; deleting the file from the latest commit does not remove it from Git history.

Review dependency updates together with the relevant lockfile and run the affected checks. This project does not publish a separate supported-release or security-backport schedule; review the current default branch and verification evidence when assessing a deployment.
