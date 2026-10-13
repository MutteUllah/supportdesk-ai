BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    email VARCHAR(254) NOT NULL, 
    password_hash TEXT NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (email)
);

CREATE INDEX ix_users_created_at ON users (created_at);

CREATE TABLE workspaces (
    name VARCHAR(100) NOT NULL, 
    public_id VARCHAR(36) NOT NULL, 
    bot_name VARCHAR(100) NOT NULL, 
    welcome VARCHAR(500) NOT NULL, 
    color VARCHAR(7) NOT NULL, 
    origins JSON NOT NULL, 
    embedding_identity VARCHAR(200) NOT NULL, 
    quota_day VARCHAR(10) NOT NULL, 
    quota_used INTEGER NOT NULL, 
    quota_limit INTEGER NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (public_id)
);

CREATE INDEX ix_workspaces_created_at ON workspaces (created_at);

CREATE TABLE documents (
    name VARCHAR(200) NOT NULL, 
    active_version_id VARCHAR(36), 
    deleted BOOLEAN NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    UNIQUE (workspace_id, id)
);

CREATE INDEX ix_documents_created_at ON documents (created_at);

CREATE INDEX ix_documents_workspace_id ON documents (workspace_id);

CREATE TABLE memberships (
    user_id VARCHAR(36) NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (role in ('owner','administrator','support-agent')), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    UNIQUE (workspace_id, user_id)
);

CREATE INDEX ix_memberships_created_at ON memberships (created_at);

CREATE INDEX ix_memberships_workspace_id ON memberships (workspace_id);

CREATE TABLE sessions (
    user_id VARCHAR(36) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    csrf VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (token_hash)
);

CREATE INDEX ix_sessions_created_at ON sessions (created_at);

CREATE INDEX ix_sessions_expires_at ON sessions (expires_at);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE TABLE usage_events (
    model VARCHAR(200) NOT NULL, 
    input_tokens INTEGER NOT NULL, 
    output_tokens INTEGER NOT NULL, 
    latency_ms INTEGER NOT NULL, 
    estimated_cost FLOAT NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
);

CREATE INDEX ix_usage_events_created_at ON usage_events (created_at);

CREATE INDEX ix_usage_events_workspace_id ON usage_events (workspace_id);

CREATE TABLE widget_sessions (
    token_hash VARCHAR(64) NOT NULL, 
    origin VARCHAR(300) NOT NULL, 
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    UNIQUE (token_hash), 
    UNIQUE (workspace_id, id)
);

CREATE INDEX ix_widget_sessions_created_at ON widget_sessions (created_at);

CREATE INDEX ix_widget_sessions_expires_at ON widget_sessions (expires_at);

CREATE INDEX ix_widget_sessions_workspace_id ON widget_sessions (workspace_id);

CREATE TABLE conversations (
    visitor_id VARCHAR(36), 
    state VARCHAR(20) NOT NULL, 
    agent_id VARCHAR(36), 
    revision INTEGER NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (state in ('bot','pending-human','human')), 
    FOREIGN KEY(agent_id) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(workspace_id, visitor_id) REFERENCES widget_sessions (workspace_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    UNIQUE (workspace_id, id)
);

CREATE INDEX ix_conversations_created_at ON conversations (created_at);

CREATE INDEX ix_conversations_workspace_id ON conversations (workspace_id);

CREATE TABLE document_versions (
    document_id VARCHAR(36) NOT NULL, 
    number INTEGER NOT NULL, 
    filename VARCHAR(200) NOT NULL, 
    storage_key VARCHAR(300) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    error VARCHAR(500), 
    attempts INTEGER NOT NULL, 
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    embedding_identity VARCHAR(200) NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(workspace_id, document_id) REFERENCES documents (workspace_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    UNIQUE (document_id, number), 
    UNIQUE (storage_key), 
    UNIQUE (workspace_id, id)
);

CREATE INDEX ix_document_versions_created_at ON document_versions (created_at);

CREATE INDEX ix_document_versions_workspace_id ON document_versions (workspace_id);

CREATE TABLE document_chunks (
    version_id VARCHAR(36) NOT NULL, 
    ordinal INTEGER NOT NULL, 
    page INTEGER NOT NULL, 
    section VARCHAR(200) NOT NULL, 
    text TEXT NOT NULL, 
    embedding VECTOR NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(workspace_id, version_id) REFERENCES document_versions (workspace_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    UNIQUE (version_id, ordinal), 
    UNIQUE (workspace_id, id)
);

CREATE INDEX ix_document_chunks_created_at ON document_chunks (created_at);

CREATE INDEX ix_document_chunks_workspace_id ON document_chunks (workspace_id);

CREATE TABLE messages (
    conversation_id VARCHAR(36) NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    content TEXT NOT NULL, 
    request_key VARCHAR(80), 
    status VARCHAR(20) NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(workspace_id, conversation_id) REFERENCES conversations (workspace_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    UNIQUE (conversation_id, request_key, role), 
    UNIQUE (workspace_id, id)
);

CREATE INDEX ix_messages_created_at ON messages (created_at);

CREATE INDEX ix_messages_workspace_id ON messages (workspace_id);

CREATE INDEX message_history ON messages (conversation_id, created_at);

CREATE TABLE tickets (
    conversation_id VARCHAR(36) NOT NULL, 
    action_key VARCHAR(80) NOT NULL, 
    subject VARCHAR(200) NOT NULL, 
    description TEXT NOT NULL, 
    email VARCHAR(254), 
    status VARCHAR(20) NOT NULL, 
    assignee_id VARCHAR(36), 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status in ('open','in progress','resolved')), 
    FOREIGN KEY(assignee_id) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(workspace_id, conversation_id) REFERENCES conversations (workspace_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    UNIQUE (conversation_id, action_key), 
    UNIQUE (workspace_id, id)
);

CREATE INDEX ix_tickets_created_at ON tickets (created_at);

CREATE INDEX ix_tickets_workspace_id ON tickets (workspace_id);

CREATE TABLE message_citations (
    message_id VARCHAR(36) NOT NULL, 
    document_id VARCHAR(36) NOT NULL, 
    version_id VARCHAR(36) NOT NULL, 
    chunk_id VARCHAR(36) NOT NULL, 
    page INTEGER NOT NULL, 
    section VARCHAR(200) NOT NULL, 
    excerpt TEXT NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(workspace_id, document_id) REFERENCES documents (workspace_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id, message_id) REFERENCES messages (workspace_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id, version_id) REFERENCES document_versions (workspace_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
);

CREATE INDEX ix_message_citations_created_at ON message_citations (created_at);

CREATE INDEX ix_message_citations_workspace_id ON message_citations (workspace_id);

CREATE TABLE tool_executions (
    conversation_id VARCHAR(36) NOT NULL, 
    action_key VARCHAR(80) NOT NULL, 
    ticket_id VARCHAR(36) NOT NULL, 
    verified BOOLEAN NOT NULL, 
    workspace_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(workspace_id, conversation_id) REFERENCES conversations (workspace_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id, ticket_id) REFERENCES tickets (workspace_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE, 
    UNIQUE (conversation_id, action_key)
);

CREATE INDEX ix_tool_executions_created_at ON tool_executions (created_at);

CREATE INDEX ix_tool_executions_workspace_id ON tool_executions (workspace_id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

