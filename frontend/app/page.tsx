"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Workspace = {
  id: string;
  name: string;
  public_id: string;
  role: string;
  bot_name: string;
  welcome: string;
  color: string;
  origins: string[];
};
type Citation = { id: string; page: number; available: boolean };
type Message = {
  id: string;
  role: string;
  content: string;
  citations: Citation[];
};
type Conversation = {
  id: string;
  state: string;
  agent_id: string | null;
  messages?: Message[];
  created_at: string;
};
type Doc = {
  id: string;
  name: string;
  active_version_id: string | null;
  versions: {
    id: string;
    number: number;
    status: string;
    error: string | null;
  }[];
};
type Ticket = {
  id: string;
  subject: string;
  description: string;
  email: string | null;
  status: string;
  assignee_id: string | null;
  conversation_id: string;
};
type Member = { id: string; user_id: string; email: string; role: string };
type Overview = {
  documents: number;
  conversations: number;
  tickets: number;
  messages_today: number;
  quota: number;
  model_mode: string;
  recent_usage: {
    id: string;
    model: string;
    latency_ms: number;
    estimated_cost: number;
    created_at: string;
  }[];
};
type User = { id: string; email: string; csrf: string; model_mode?: string };
const pages = [
  "Overview",
  "Documents",
  "Playground",
  "Conversations",
  "Support inbox",
  "Tickets",
  "Members",
  "Settings",
];
const icons = ["◫", "▤", "✧", "◷", "↳", "▱", "♧", "⚙"];

export default function Dashboard() {
  const [user, setUser] = useState<User | null>(null),
    [boot, setBoot] = useState(true),
    [register, setRegister] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]),
    [wid, setWid] = useState(""),
    [page, setPage] = useState("Overview");
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [docs, setDocs] = useState<Doc[]>([]),
    [conversations, setConversations] = useState<Conversation[]>([]),
    [tickets, setTickets] = useState<Ticket[]>([]),
    [members, setMembers] = useState<Member[]>([]),
    [overview, setOverview] = useState<Overview | null>(null);
  const [selected, setSelected] = useState<Conversation | null>(null),
    [draft, setDraft] = useState(""),
    [partial, setPartial] = useState(""),
    [source, setSource] = useState<{
      document: string;
      page: number;
      excerpt: string;
    } | null>(null);
  const [ticketForm, setTicketForm] = useState(false),
    [pendingKey, setPendingKey] = useState("");
  const ws = workspaces.find((w) => w.id === wid),
    manager = ws?.role === "owner" || ws?.role === "administrator";

  const api = useCallback(
    async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
      const headers = new Headers(options.headers);
      if (!(options.body instanceof FormData))
        headers.set("Content-Type", "application/json");
      if (user?.csrf) headers.set("X-CSRF-Token", user.csrf);
      const response = await fetch(API + path, {
        ...options,
        headers,
        credentials: "include",
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.detail || "Request failed. Please retry.");
      return data as T;
    },
    [user],
  );
  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    let live = true;
    fetch(API + "/auth/me", { credentials: "include" })
      .then(async (r) => {
        if (r.ok && live) setUser(await r.json());
      })
      .catch(() => {
        if (live)
          setError("Cannot reach the API. Start the backend and refresh.");
      })
      .finally(() => {
        if (live) setBoot(false);
      });
    return () => {
      live = false;
    };
  }, []);
  const loadWorkspaces = useCallback(async () => {
    const list = await api<Workspace[]>("/workspaces");
    setWorkspaces(list);
    setWid((current) =>
      list.some((w) => w.id === current) ? current : list[0]?.id || "",
    );
  }, [api]);
  useEffect(() => {
    if (!user) return;
    let live = true;
    void api<Workspace[]>("/workspaces")
      .then((list) => {
        if (live) {
          setWorkspaces(list);
          setWid((current) =>
            list.some((w) => w.id === current) ? current : list[0]?.id || "",
          );
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [user, api]);
  const reload = useCallback(async () => {
    if (!wid) return;
    const base = "/workspaces/" + wid;
    const [d, c, t, m, o] = await Promise.all([
      api<Doc[]>(base + "/documents"),
      api<Conversation[]>(base + "/conversations"),
      api<Ticket[]>(base + "/tickets"),
      api<Member[]>(base + "/members"),
      api<Overview>(base + "/overview"),
    ]);
    setDocs(d);
    setConversations(c);
    setTickets(t);
    setMembers(m);
    setOverview(o);
  }, [wid, api]);
  useEffect(() => {
    if (!wid) return;
    const refresh = () => {
      void reload().catch((e) => setError(e.message));
    };
    const first = setTimeout(refresh, 0);
    const timer = setInterval(refresh, 7000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [wid, reload]);
  useEffect(() => {
    if (!selected?.id || !wid) return;
    const id = selected.id;
    const timer = setInterval(() => {
      void api<Conversation>(`/workspaces/${wid}/conversations/${id}`)
        .then(setSelected)
        .catch(() => {});
    }, 3000);
    return () => clearInterval(timer);
  }, [selected?.id, wid, api]);
  async function auth(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    await act(async () => {
      const u = await api<User>(register ? "/auth/register" : "/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: data.get("email"),
          password: data.get("password"),
        }),
      });
      setUser(u);
    });
  }
  async function createWorkspace(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const name = new FormData(form).get("name");
    await act(async () => {
      const w = await api<Workspace>("/workspaces", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      await loadWorkspaces();
      setWid(w.id);
      setSelected(null);
      form.reset();
      setNotice("Workspace created. Add documents to teach your assistant.");
    });
  }
  async function upload(file: File | undefined, id?: string) {
    if (!file) return;
    await act(async () => {
      const form = new FormData();
      form.set("file", file);
      await api(
        `/workspaces/${wid}/documents${id ? "/" + id + "/replace" : ""}`,
        { method: "POST", body: form },
      );
      setNotice("Upload received. The worker will process it shortly.");
      await reload();
    });
  }
  async function openConversation(id: string) {
    await act(async () =>
      setSelected(
        await api<Conversation>(`/workspaces/${wid}/conversations/${id}`),
      ),
    );
  }
  async function newConversation() {
    await act(async () => {
      const c = await api<Conversation>(`/workspaces/${wid}/conversations`, {
        method: "POST",
      });
      setSelected({ ...c, messages: [] });
      setPendingKey("");
      await reload();
    });
  }
  async function send(action = "chat", subject = "", email = "", text = draft) {
    if (!selected) return;
    const key = pendingKey || crypto.randomUUID();
    setPendingKey(key);
    await act(async () => {
      setPartial("");
      const res = await fetch(
        `${API}/workspaces/${wid}/conversations/${selected.id}/chat`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": user?.csrf || "",
          },
          body: JSON.stringify({
            text,
            request_key: key,
            action,
            subject,
            email: email || null,
            consent: action === "ticket",
          }),
        },
      );
      if (!res.ok) throw new Error((await res.json()).detail);
      const reader = res.body!.getReader(),
        decoder = new TextDecoder();
      let buffer = "",
        done = false;
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        let cut;
        while ((cut = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, cut);
          buffer = buffer.slice(cut + 2);
          const event = frame.match(/^event: (.+)$/m)?.[1],
            data = JSON.parse(frame.match(/^data: (.+)$/m)?.[1] || "{}");
          if (event === "delta") setPartial((p) => p + data.text);
          if (event === "error" || event === "interrupted")
            throw new Error(data.detail);
          if (event === "done") done = true;
        }
      }
      if (!done)
        throw new Error(
          "Connection interrupted. Retry unchanged to reuse the same request key.",
        );
      setDraft("");
      setPendingKey("");
      setPartial("");
      setTicketForm(false);
      setSelected(
        await api<Conversation>(
          `/workspaces/${wid}/conversations/${selected.id}`,
        ),
      );
      await reload();
    });
  }
  async function human(action: string) {
    if (!selected) return;
    await act(async () => {
      await api(`/workspaces/${wid}/conversations/${selected.id}/${action}`, {
        method: "POST",
        body: action === "reply" ? JSON.stringify({ text: draft }) : undefined,
      });
      if (action === "reply") setDraft("");
      setSelected(
        await api<Conversation>(
          `/workspaces/${wid}/conversations/${selected.id}`,
        ),
      );
      await reload();
    });
  }

  if (boot)
    return (
      <main className="auth-form">
        <p>Loading SupportDesk AI…</p>
      </main>
    );
  if (!user)
    return (
      <main className="auth">
        <section className="auth-story">
          <span className="eyebrow" style={{ color: "#a5c8b3" }}>
            GOOD SUPPORT STARTS HERE
          </span>
          <h1>
            A helpful answer.
            <br />A human when
            <br />
            it matters.
          </h1>
          <p>
            Bring your knowledge, conversations, and support team together in
            one calm workspace.
          </p>
          <p style={{ fontSize: 13, marginTop: 50 }}>
            Grounded in your documents. Built around your customers.
          </p>
        </section>
        <section className="auth-form">
          <div className="brand">
            <span className="logo">s</span>SupportDesk <small>AI</small>
          </div>
          <h1>{register ? "Create your account" : "Welcome back"}</h1>
          <p className="muted">
            Your next great customer conversation starts here.
          </p>
          {error && (
            <p role="alert" className="notice error">
              {error}
            </p>
          )}
          <form onSubmit={auth}>
            <label>
              Email address
              <input name="email" type="email" required autoComplete="email" />
            </label>
            <label>
              Password
              <input
                aria-label="Password"
                name="password"
                type="password"
                required
                minLength={12}
                maxLength={128}
                autoComplete={register ? "new-password" : "current-password"}
              />
              <small className="muted">At least 12 characters.</small>
            </label>
            <button className="primary" disabled={busy}>
              {busy ? "Please wait…" : register ? "Create account" : "Log in"}
            </button>
          </form>
          <button
            onClick={() => {
              setRegister(!register);
              setError("");
            }}
          >
            {register
              ? "Already registered? Log in"
              : "New here? Create an account"}
          </button>
        </section>
      </main>
    );

  const chatPanel = (
    <div className="panel">
      <div className="row space">
        <h2>
          {selected
            ? "Conversation " + selected.id.slice(0, 8)
            : "Your chatbot playground"}
        </h2>
        <button onClick={newConversation} disabled={busy}>
          + New conversation
        </button>
      </div>
      {selected ? (
        <>
          <span className={"badge " + (selected.state === "bot" ? "" : "warn")}>
            {selected.state}
          </span>
          <div className="chatlog" aria-live="polite">
            {!selected.messages?.length && (
              <p className="muted">
                {ws?.welcome} Ask a question covered by your documents.
              </p>
            )}
            {selected.messages?.map((m) => (
              <div className={"message " + m.role} key={m.id}>
                <small>{m.role}</small>
                {m.content}
                <div>
                  {m.citations.map((c) => (
                    <button
                      className="citation"
                      key={c.id}
                      disabled={!c.available}
                      onClick={() =>
                        act(async () =>
                          setSource(
                            await api(`/workspaces/${wid}/sources/${c.id}`),
                          ),
                        )
                      }
                    >
                      {c.available
                        ? `Source · page ${c.page}`
                        : "Source removed"}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            {partial && (
              <div className="message">
                <small>Receiving</small>
                {partial}
              </div>
            )}
          </div>
          <form
            className="chat-form"
            onSubmit={(e) => {
              e.preventDefault();
              void (page === "Support inbox" ? human("reply") : send());
            }}
          >
            <input
              aria-label="Message"
              disabled={busy}
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                setPendingKey("");
              }}
              placeholder={
                page === "Support inbox"
                  ? "Write a human reply…"
                  : "Ask about shipping, returns, or a product…"
              }
              required
              maxLength={4000}
            />
            <button
              className="primary"
              disabled={
                busy ||
                (page === "Support inbox" && selected.agent_id !== user.id)
              }
            >
              {busy ? "Working…" : "Send"}
            </button>
          </form>
          <div className="row" style={{ marginTop: 14 }}>
            {page === "Support inbox" ? (
              <>
                <button disabled={busy} onClick={() => human("claim")}>
                  Claim conversation
                </button>
                <button
                  disabled={busy || selected.agent_id !== user.id}
                  onClick={() => human("release")}
                >
                  Return to bot
                </button>
              </>
            ) : (
              <>
                <button
                  disabled={busy}
                  onClick={() => {
                    setPendingKey("");
                    setTicketForm(true);
                  }}
                >
                  Create support ticket
                </button>
                <button
                  disabled={busy}
                  onClick={() => {
                    setPendingKey("");
                    void send("handoff", "", "", "I would like human support.");
                  }}
                >
                  Request a human
                </button>
              </>
            )}
            {manager && (
              <button
                className="danger"
                disabled={busy}
                onClick={() => {
                  if (confirm("Delete this conversation and its tickets?"))
                    void act(async () => {
                      await api(
                        `/workspaces/${wid}/conversations/${selected.id}`,
                        { method: "DELETE" },
                      );
                      setSelected(null);
                      await reload();
                    });
                }}
              >
                Delete
              </button>
            )}
          </div>
        </>
      ) : (
        <div className="empty">
          Start a conversation to test answers, citations, and handoff.
        </div>
      )}
    </div>
  );

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="logo">s</span>SupportDesk <small>AI</small>
        </div>
        <div>
          <p className="eyebrow">WORKSPACE</p>
          <nav className="nav">
            {pages.map((p, i) => (
              <button
                key={p}
                className={page === p ? "active" : ""}
                onClick={() => {
                  setPage(p);
                  setError("");
                  setNotice("");
                }}
              >
                <span aria-hidden>{icons[i]}</span>
                {p}
              </button>
            ))}
          </nav>
        </div>
        <div className="sidefoot">
          <span className="badge">{ws?.role || "New account"}</span>
          <p className="muted" style={{ overflowWrap: "anywhere" }}>
            {user.email}
          </p>
          <button
            onClick={() =>
              act(async () => {
                await api("/auth/logout", { method: "POST" });
                setUser(null);
                setRegister(false);
                setSelected(null);
                setWorkspaces([]);
                setWid("");
              })
            }
          >
            Log out
          </button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <span className="muted">Your customer support, connected.</span>
          <div className="row">
            <span className="badge warn">
              {overview?.model_mode === "openai"
                ? "Live provider"
                : "MOCK · no LLM inference"}
            </span>
            <select
              aria-label="Workspace"
              value={wid}
              onChange={(e) => {
                setWid(e.target.value);
                setSelected(null);
                setOverview(null);
                setDocs([]);
                setTickets([]);
                setConversations([]);
              }}
            >
              <option value="" disabled>
                Select workspace
              </option>
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>
        </header>
        <div className="heading">
          <div>
            <span className="eyebrow">{ws?.name || "GET STARTED"}</span>
            <h1>{page}</h1>
            <span className="muted">
              {page === "Overview"
                ? "A little clarity on every customer conversation."
                : page === "Documents"
                  ? "The knowledge behind every helpful answer."
                  : "Everything your support team needs, in one place."}
            </span>
          </div>
          {wid && (
            <button disabled={busy} onClick={() => act(reload)}>
              Refresh
            </button>
          )}
        </div>
        {error && (
          <div role="alert" className="notice error">
            {error}
          </div>
        )}
        {notice && (
          <div role="status" className="notice">
            {notice}
          </div>
        )}
        {(!wid || page === "Settings") && (
          <section className="panel">
            <h2>Create a workspace</h2>
            <form className="row" onSubmit={createWorkspace}>
              <input
                name="name"
                aria-label="New workspace name"
                required
                maxLength={100}
                placeholder="Business name"
                style={{ maxWidth: 350 }}
              />
              <button className="primary" disabled={busy}>
                Create workspace
              </button>
            </form>
          </section>
        )}
        {wid && page === "Overview" && (
          <>
            <section className="hero">
              <div>
                <span className="eyebrow" style={{ color: "#a5c8b3" }}>
                  KNOWLEDGE MEETS CONVERSATION
                </span>
                <h2 style={{ marginTop: 15 }}>
                  Make every answer
                  <br />
                  feel like a helping hand.
                </h2>
                <p>
                  Upload your business knowledge, test your assistant, and be
                  there when a customer needs a person.
                </p>
                <button
                  onClick={() =>
                    setPage(docs.length ? "Playground" : "Documents")
                  }
                >
                  {docs.length
                    ? "Try your assistant →"
                    : "Add your first document →"}
                </button>
              </div>
              <div className="hero-art" aria-hidden>
                <span>✧ &nbsp; Your knowledge. A helpful answer.</span>
                <div />
                <div />
                <div />
              </div>
            </section>
            <div className="stats">
              {[
                ["Conversations", overview?.conversations],
                ["Knowledge documents", overview?.documents],
                ["Support tickets", overview?.tickets],
                ["Messages today", overview?.messages_today],
              ].map(([label, value]) => (
                <div className="panel stat" key={label}>
                  <span className="muted">{label}</span>
                  <strong>{value ?? "—"}</strong>
                </div>
              ))}
            </div>
            <div className="grid">
              <section className="panel">
                <h2>Daily message allowance</h2>
                <p className="muted">
                  {overview?.messages_today || 0} of {overview?.quota || 0}{" "}
                  messages used. Resets at midnight UTC.
                </p>
                <div className="progress">
                  <i
                    style={{
                      width:
                        Math.min(
                          100,
                          (100 * (overview?.messages_today || 0)) /
                            (overview?.quota || 1),
                        ) + "%",
                    }}
                  />
                </div>
                <p className="muted">
                  Usage is enforced by the backend for this workspace.
                </p>
              </section>
              <section className="panel">
                <h2>Recent activity</h2>
                {overview?.recent_usage.length ? (
                  overview.recent_usage.slice(0, 5).map((u) => (
                    <div className="listitem row space" key={u.id}>
                      <span>
                        {u.model}
                        <br />
                        <small className="muted">
                          {new Date(u.created_at + "Z").toLocaleString()}
                        </small>
                      </span>
                      <span>
                        {u.latency_ms} ms
                        <br />
                        <small className="muted">
                          ${u.estimated_cost.toFixed(6)} est.
                        </small>
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="empty">
                    Your first conversation will appear here.
                  </div>
                )}
              </section>
            </div>
          </>
        )}
        {wid && page === "Documents" && (
          <section className="panel">
            <h2>Knowledge library</h2>
            {manager && (
              <label className="upload">
                Upload a document{" "}
                <span className="muted">
                  Text-based PDF, TXT, or Markdown · up to 10 MB
                </span>
                <input
                  type="file"
                  aria-label="Upload document"
                  accept=".pdf,.txt,.md"
                  disabled={busy}
                  onChange={(e) => {
                    void upload(e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
              </label>
            )}
            {!docs.length ? (
              <div className="empty">
                No documents yet. Add your shipping, returns, and product
                policies.
              </div>
            ) : (
              docs.map((d) => (
                <div className="listitem" key={d.id}>
                  <div className="row space">
                    <h3>▤ &nbsp;{d.name}</h3>
                    <span className="badge">{d.versions[0]?.status}</span>
                  </div>
                  {d.versions.map((v) => (
                    <p className="muted" key={v.id}>
                      Version {v.number} · {v.status}
                      {d.active_version_id === v.id ? " · searchable" : ""}
                      {v.error && <span className="danger"> · {v.error}</span>}
                    </p>
                  ))}
                  <div className="row">
                    <a
                      href={`${API}/workspaces/${wid}/documents/${d.id}/download`}
                    >
                      Download active version
                    </a>
                    {manager && (
                      <>
                        <label style={{ margin: 0 }}>
                          Replace
                          <input
                            type="file"
                            aria-label={"Replace " + d.name}
                            accept=".pdf,.txt,.md"
                            disabled={busy}
                            onChange={(e) => {
                              void upload(e.target.files?.[0], d.id);
                              e.target.value = "";
                            }}
                          />
                        </label>
                        <button
                          className="danger"
                          disabled={busy}
                          onClick={() => {
                            if (
                              confirm(
                                "Delete this document and revoke its citations?",
                              )
                            )
                              void act(async () => {
                                await api(
                                  `/workspaces/${wid}/documents/${d.id}`,
                                  { method: "DELETE" },
                                );
                                await reload();
                              });
                          }}
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))
            )}
          </section>
        )}
        {wid && page === "Playground" && chatPanel}
        {wid && (page === "Conversations" || page === "Support inbox") && (
          <div className="split">
            <section className="panel conversation-list">
              <h2>
                {page === "Support inbox"
                  ? "Needs a human"
                  : "All conversations"}
              </h2>
              {conversations
                .filter((c) => page !== "Support inbox" || c.state !== "bot")
                .map((c) => (
                  <button key={c.id} onClick={() => openConversation(c.id)}>
                    <strong>{c.id.slice(0, 8)}</strong>
                    <p className="muted">
                      {c.state} ·{" "}
                      {new Date(c.created_at + "Z").toLocaleDateString()}
                    </p>
                  </button>
                ))}
              {!conversations.filter(
                (c) => page !== "Support inbox" || c.state !== "bot",
              ).length && (
                <p className="muted">No conversations in this view.</p>
              )}
            </section>
            {chatPanel}
          </div>
        )}
        {wid && page === "Tickets" && (
          <section className="panel">
            <h2>
              Support tickets <span className="badge">{tickets.length}</span>
            </h2>
            {!tickets.length ? (
              <div className="empty">
                Tickets appear when a customer explicitly requests one.
              </div>
            ) : (
              tickets.map((t) => (
                <div className="listitem" key={t.id}>
                  <div className="row space">
                    <h3>{t.subject}</h3>
                    <span className="muted">#{t.id.slice(0, 8)}</span>
                  </div>
                  <p>{t.description}</p>
                  <p className="muted">
                    {t.email || "No contact email supplied"}
                  </p>
                  <div className="row">
                    <select
                      aria-label={"Status " + t.subject}
                      style={{ width: 170 }}
                      value={t.status}
                      onChange={(e) =>
                        act(async () => {
                          await api(`/workspaces/${wid}/tickets/${t.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({
                              status: e.target.value,
                              assignee_id: t.assignee_id,
                            }),
                          });
                          await reload();
                        })
                      }
                    >
                      {["open", "in progress", "resolved"].map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                    <select
                      aria-label={"Assignee " + t.subject}
                      style={{ width: 240 }}
                      value={t.assignee_id || ""}
                      onChange={(e) =>
                        act(async () => {
                          await api(`/workspaces/${wid}/tickets/${t.id}`, {
                            method: "PATCH",
                            body: JSON.stringify({
                              status: t.status,
                              assignee_id: e.target.value || null,
                            }),
                          });
                          await reload();
                        })
                      }
                    >
                      <option value="">Unassigned</option>
                      {members.map((m) => (
                        <option key={m.id} value={m.user_id}>
                          {m.email}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => {
                        setPage("Conversations");
                        void openConversation(t.conversation_id);
                      }}
                    >
                      Open conversation
                    </button>
                  </div>
                </div>
              ))
            )}
          </section>
        )}
        {wid && page === "Members" && (
          <section className="panel">
            <h2>Your team</h2>
            {ws?.role === "owner" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.currentTarget,
                    data = new FormData(form);
                  void act(async () => {
                    await api(`/workspaces/${wid}/members`, {
                      method: "POST",
                      body: JSON.stringify({
                        email: data.get("email"),
                        role: data.get("role"),
                      }),
                    });
                    form.reset();
                    await reload();
                    setNotice("Member added or role updated.");
                  });
                }}
                className="row"
              >
                <input
                  name="email"
                  type="email"
                  placeholder="Registered user's email"
                  required
                  style={{ maxWidth: 280 }}
                />
                <select
                  name="role"
                  aria-label="Member role"
                  style={{ width: 200 }}
                >
                  <option value="support-agent">Support agent</option>
                  <option value="administrator">Administrator</option>
                </select>
                <button className="primary" disabled={busy}>
                  Add / update member
                </button>
              </form>
            )}
            {members.map((m) => (
              <div className="listitem row space" key={m.id}>
                <span>{m.email}</span>
                <div className="row">
                  <span className="badge">{m.role}</span>
                  {ws?.role === "owner" && m.role !== "owner" && (
                    <button
                      className="danger"
                      onClick={() =>
                        act(async () => {
                          await api(`/workspaces/${wid}/members/${m.id}`, {
                            method: "DELETE",
                          });
                          await reload();
                        })
                      }
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
            ))}
            <p className="muted">
              Owners manage settings and members. Administrators manage
              knowledge and support. Support agents handle conversations and
              tickets.
            </p>
          </section>
        )}
        {wid && page === "Settings" && ws && (
          <>
            <section className="panel">
              <h2>Business & chatbot</h2>
              <form
                key={ws.id}
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  void act(async () => {
                    await api(`/workspaces/${wid}`, {
                      method: "PATCH",
                      body: JSON.stringify({
                        name: f.get("name"),
                        bot_name: f.get("bot_name"),
                        welcome: f.get("welcome"),
                        color: f.get("color"),
                        origins: String(f.get("origins"))
                          .split("\n")
                          .map((x) => x.trim())
                          .filter(Boolean),
                      }),
                    });
                    await loadWorkspaces();
                    setNotice("Settings saved.");
                  });
                }}
              >
                <div className="grid">
                  <label>
                    Business name
                    <input
                      name="name"
                      defaultValue={ws.name}
                      required
                      maxLength={100}
                    />
                  </label>
                  <label>
                    Chatbot name
                    <input
                      name="bot_name"
                      defaultValue={ws.bot_name}
                      required
                      maxLength={100}
                    />
                  </label>
                </div>
                <label>
                  Welcome message
                  <textarea
                    name="welcome"
                    defaultValue={ws.welcome}
                    required
                    maxLength={500}
                  />
                </label>
                <label>
                  Brand color
                  <input
                    type="color"
                    name="color"
                    defaultValue={ws.color}
                    style={{ width: 100, height: 45 }}
                  />
                </label>
                <label>
                  Permitted website origins (one per line)
                  <textarea
                    name="origins"
                    defaultValue={ws.origins.join("\n")}
                    placeholder="http://localhost:3001"
                  />
                </label>
                <button
                  className="primary"
                  disabled={busy || ws.role !== "owner"}
                >
                  Save settings
                </button>
                {ws.role !== "owner" && (
                  <p className="muted">
                    Only the workspace owner can save settings.
                  </p>
                )}
              </form>
            </section>
            <section className="panel">
              <h2>Install your chat widget</h2>
              <p className="muted">
                Add your website origin above, then paste this snippet before
                the closing body tag.
              </p>
              <pre>{`<script src="${API}/widget/loader.js" data-workspace="${ws.public_id}" defer></script>`}</pre>
              <button
                onClick={() =>
                  act(async () => {
                    await navigator.clipboard.writeText(
                      `<script src="${API}/widget/loader.js" data-workspace="${ws.public_id}" defer></script>`,
                    );
                    setNotice("Embed snippet copied.");
                  })
                }
              >
                Copy snippet
              </button>
            </section>
          </>
        )}
      </main>
      {source && (
        <dialog open aria-label="Citation source">
          <h2>
            {source.document} · page {source.page}
          </h2>
          <p className="source-text">{source.excerpt}</p>
          <button onClick={() => setSource(null)}>Close source</button>
        </dialog>
      )}
      {ticketForm && (
        <dialog open aria-label="Create support ticket">
          <h2>Create a support ticket</h2>
          <p className="muted">
            Submitting this form explicitly requests a ticket for this
            conversation.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void send(
                "ticket",
                String(f.get("subject")),
                String(f.get("email")),
                String(f.get("description")),
              );
            }}
          >
            <label>
              Subject
              <input name="subject" required maxLength={200} />
            </label>
            <label>
              Issue description
              <textarea
                name="description"
                required
                maxLength={4000}
                defaultValue={draft}
              />
            </label>
            <label>
              Contact email (optional)
              <input name="email" type="email" />
            </label>
            <div className="row">
              <button className="primary" disabled={busy}>
                Confirm & create ticket
              </button>
              <button type="button" onClick={() => setTicketForm(false)}>
                Cancel
              </button>
            </div>
          </form>
        </dialog>
      )}
    </div>
  );
}
