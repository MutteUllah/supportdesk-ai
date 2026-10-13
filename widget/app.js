/* Visitor bearer tokens are scoped to one visitor; no dashboard token is stored here. */
const $ = (id) => document.getElementById(id);
const publicId = location.pathname.split("/").pop();
const embeddingOrigin = decodeURIComponent(location.hash.slice(1));
const key = "supportdesk-visitor:" + publicId + ":" + embeddingOrigin;
let session = null,
  config = null,
  busy = false,
  requestKey = null;
try {
  session = JSON.parse(localStorage.getItem(key) || "null");
} catch {
  /* Storage may be blocked in third-party frames. */
}
async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(session ? { Authorization: "Bearer " + session.token } : {}),
      ...options.headers,
    },
  });
  const data = await res.json();
  if (!res.ok) throw Error(data.detail || "Please retry.");
  return data;
}
function showError(error) {
  $("error").textContent = error.message || String(error);
}
async function refresh() {
  if (!session || busy) return;
  const data = await api("/visitor/conversations/" + session.conversation_id);
  const previousScroll = $("messages").scrollTop;
  const nearBottom =
    $("messages").scrollHeight - previousScroll - $("messages").clientHeight <
    60;
  $("messages").replaceChildren();
  if (!data.messages.length) {
    const welcome = document.createElement("p");
    welcome.textContent = config.welcome;
    $("messages").append(welcome);
  }
  for (const message of data.messages) {
    const item = document.createElement("div");
    item.className = "message " + message.role;
    const role = document.createElement("small");
    role.textContent = message.role;
    const content = document.createElement("span");
    content.textContent = message.content;
    item.append(role, content);
    for (const cite of message.citations) {
      const b = document.createElement("button");
      b.textContent = cite.available
        ? "Source · page " + cite.page
        : "Source removed";
      b.disabled = !cite.available;
      b.onclick = async () => {
        try {
          const s = await api("/visitor/sources/" + cite.id);
          $("source-name").textContent = s.document + " · page " + s.page;
          $("source-text").textContent = s.excerpt;
          $("source").showModal();
        } catch (e) {
          showError(e);
        }
      };
      item.append(document.createElement("br"), b);
    }
    $("messages").append(item);
  }
  $("messages").scrollTop = nearBottom
    ? $("messages").scrollHeight
    : previousScroll;
  $("status").textContent =
    data.state === "bot"
      ? "Assistant ready"
      : data.state === "human"
        ? "A human agent has joined."
        : "Waiting for a human. No agent has joined yet.";
}
async function start() {
  config = await api("/public/" + publicId + "/config");
  $("name").textContent = config.bot_name;
  $("mode").textContent =
    config.model_mode === "mock"
      ? "MOCK MODE · Extracted evidence, no LLM inference"
      : "Answers grounded in our documents";
  document.documentElement.style.setProperty("--brand", config.color);
  if (!session || Date.parse(session.expires_at) <= Date.now()) {
    session = await api("/public/" + publicId + "/session", {
      method: "POST",
      body: JSON.stringify({ origin: embeddingOrigin }),
    });
    try {
      localStorage.setItem(key, JSON.stringify(session));
    } catch {
      $("status").textContent =
        "Your browser blocks storage: continuity is limited to this page.";
    }
  }
  await refresh();
  $("send").disabled = false;
  $("ticket").disabled = false;
  $("human").disabled = false;
}
async function send(payload) {
  if (busy || !session) return;
  busy = true;
  $("send").disabled = true;
  $("error").textContent = "";
  requestKey = requestKey || crypto.randomUUID();
  let complete = false;
  try {
    const res = await fetch(
      "/visitor/conversations/" + session.conversation_id + "/chat",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + session.token,
        },
        body: JSON.stringify({ ...payload, request_key: requestKey }),
      },
    );
    if (!res.ok) throw Error((await res.json()).detail);
    const preview = document.createElement("div");
    preview.className = "message";
    preview.textContent = "Working…";
    $("messages").append(preview);
    const reader = res.body.getReader(),
      decoder = new TextDecoder();
    let buffer = "",
      content = "";
    while (true) {
      const part = await reader.read();
      if (part.done) break;
      buffer += decoder.decode(part.value, { stream: true });
      let end;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const event = frame.match(/^event: (.+)$/m)?.[1],
          data = JSON.parse(frame.match(/^data: (.+)$/m)?.[1] || "{}");
        if (event === "error" || event === "interrupted")
          throw Error(data.detail);
        if (event === "delta") {
          content += data.text;
          preview.textContent = content;
        }
        if (event === "done") complete = true;
      }
    }
    if (!complete)
      throw Error(
        "Connection interrupted. Retry unchanged; your request key is preserved.",
      );
    requestKey = null;
    $("text").value = "";
    $("ticket-dialog").close();
  } catch (e) {
    showError(e);
  } finally {
    busy = false;
    $("send").disabled = false;
    await refresh().catch(showError);
  }
}
$("chat").onsubmit = (e) => {
  e.preventDefault();
  void send({ text: $("text").value, action: "chat" });
};
$("text").oninput = () => {
  requestKey = null;
};
$("ticket").onclick = () => {
  requestKey = null;
  $("ticket-dialog").showModal();
};
$("human").onclick = () => {
  requestKey = null;
  void send({ text: "I would like human support.", action: "handoff" });
};
$("ticket-form").onsubmit = (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  void send({
    text: f.get("description"),
    subject: f.get("subject"),
    email: f.get("email") || null,
    action: "ticket",
    consent: true,
  });
};
$("cancel").onclick = () => $("ticket-dialog").close();
$("close-source").onclick = () => $("source").close();
$("restart").onclick = () => {
  if (
    !busy &&
    confirm(
      "Start a new visitor session? Existing history will no longer be accessible in this browser.",
    )
  ) {
    session = null;
    requestKey = null;
    try {
      localStorage.removeItem(key);
    } catch {}
    void start().catch(showError);
  }
};
void start().catch(showError);
setInterval(() => {
  void refresh().catch(showError);
}, 3000);
