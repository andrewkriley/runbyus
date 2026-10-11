const state = {
  latest: null,
  threadId: "",
  threads: [],
};

async function api(path, payload) {
  const opts = payload === undefined
    ? {}
    : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) };
  const resp = await fetch(path, opts);
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error || resp.statusText);
  }
  return data;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function pill(text, kind) {
  return `<span class="pill ${kind || ""}">${esc(text)}</span>`;
}

function hashThread(threadId) {
  const url = new URL(window.location.href);
  if (threadId) url.hash = `thread=${threadId}`;
  else url.hash = "";
  history.replaceState(null, "", url);
}

function threadFromHash() {
  const raw = (window.location.hash || "").replace(/^#/, "");
  const match = raw.match(/(?:^|&)thread=([^&]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function renderChat(item, pending) {
  const turns = (item && item.chat) || [];
  const parts = turns.map((turn) => {
    const kind = turn.kind === "approval" ? "approval" : turn.role;
    const who = turn.kind === "approval"
      ? "Needs approval"
      : turn.role === "human" ? "You" : "Assistant";
    return `
      <article class="bubble ${kind}">
        <p class="who">${who}</p>
        <p>${esc(turn.content)}</p>
      </article>
    `;
  });
  if (pending) {
    parts.push(`<article class="bubble pending"><p class="who">Assistant</p><p>Thinking…</p></article>`);
  }
  if (!parts.length) return `<p class="muted empty">Waiting for a human turn.</p>`;
  return parts.join("");
}

function renderMeta(item) {
  if (!item) return "";
  return [
    item.state ? pill(item.state, item.state === "done" ? "success" : item.state === "awaiting_approval" ? "warning" : "") : "",
    item.space ? pill(item.space) : "",
    item.provider ? pill(item.provider) : "",
    item.model ? pill(item.model) : "",
    pill(item.runtime || "pydanticai"),
  ].join("");
}

function renderHistory() {
  const list = document.querySelector("[data-history-list]");
  if (!state.threads.length) {
    list.innerHTML = `<p class="muted empty">No chats yet.</p>`;
    return;
  }
  list.innerHTML = state.threads.map((row) => {
    const active = row.thread_id === state.threadId ? "active" : "";
    return `
      <button type="button" class="history-item ${active}" data-pickup="${esc(row.thread_id)}">
        <span class="history-title">${esc(row.title || "New chat")}</span>
        <span class="history-preview">${esc(row.preview || "")}</span>
        ${row.state ? pill(row.state, row.state === "done" ? "success" : row.state === "awaiting_approval" ? "warning" : "") : ""}
      </button>
    `;
  }).join("");
  list.querySelectorAll("[data-pickup]").forEach((btn) => {
    btn.addEventListener("click", () => pickup(btn.getAttribute("data-pickup")));
  });
}

function renderInspect(sess) {
  const summary = document.querySelector("[data-inspect-session]");
  const tree = document.querySelector("[data-inspect-tree]");
  if (!sess || !sess.session_id) {
    summary.textContent = "No session yet.";
    tree.innerHTML = "";
    return;
  }
  summary.innerHTML = [
    `<span class="badge session">session</span> ${esc(sess.title || sess.session_id)}`,
  ].join("");
  const spansByItem = {};
  for (const span of sess.spans || []) {
    const key = (span.metadata && span.metadata.work_item_id) || "";
    if (!spansByItem[key]) spansByItem[key] = [];
    spansByItem[key].push(span);
  }
  const traces = sess.traces || [];
  if (!traces.length && !(sess.spans || []).length) {
    tree.innerHTML = `<p class="muted empty">No traces yet.</p>`;
    return;
  }
  tree.innerHTML = traces.map((trace) => {
    const itemId = trace.work_item_id;
    const child = (spansByItem[itemId] || []).map((span) => {
      const label = span.name ? `${span.kind} · ${span.name}` : span.kind;
      return `<div class="row indent"><span class="badge span">span</span> ${esc(label)} <span class="muted">${esc(span.content || "")}</span></div>`;
    }).join("");
    return `
      <div class="row">
        <span class="badge trace">trace</span> ${esc(itemId)}
      </div>
      ${child}
    `;
  }).join("");
}

function syncButtons(item) {
  const waiting = item && item.state === "awaiting_approval" && item.approval && !item.approval.decision;
  const approved = item && item.state === "awaiting_approval" && item.approval && item.approval.decision === "approved";
  document.querySelector("[data-approve]").disabled = !waiting;
  document.querySelector("[data-deny]").disabled = !waiting;
  document.querySelector("[data-resume]").disabled = !approved;
}

function showItem(item, pending) {
  state.latest = item || state.latest;
  if (item && item.thread_id) {
    state.threadId = item.thread_id;
    hashThread(item.thread_id);
  }
  const thread = document.querySelector("[data-product-thread]");
  thread.innerHTML = renderChat(item, pending);
  thread.scrollTop = thread.scrollHeight;
  document.querySelector("[data-product-meta]").innerHTML = renderMeta(item);
  const title = (item && item.title) || (state.threads.find((row) => row.thread_id === state.threadId) || {}).title;
  if (title) document.querySelector("[data-product-title]").textContent = title;
  document.querySelector("[data-product-error]").textContent = "";
  syncButtons(item);
}

function showConversation(convo) {
  if (convo && convo.thread_id) {
    state.threadId = convo.thread_id;
    hashThread(convo.thread_id);
  }
  if (convo && convo.title) {
    document.querySelector("[data-product-title]").textContent = convo.title;
  }
  if (convo && convo.latest) {
    showItem({ ...convo.latest, chat: convo.chat, title: convo.title });
    return;
  }
  showItem({ chat: (convo && convo.chat) || [], state: "", runtime: "pydanticai", thread_id: convo && convo.thread_id, title: convo && convo.title });
}

async function loadThreads() {
  state.threads = await api("/api/product/threads?channel=web");
  renderHistory();
}

async function loadSession(threadId) {
  if (!threadId) {
    renderInspect(null);
    return;
  }
  try {
    renderInspect(await api(`/api/product/session?thread_id=${encodeURIComponent(threadId)}`));
  } catch (_err) {
    renderInspect(null);
  }
}

async function pickup(threadId) {
  state.threadId = threadId || "";
  hashThread(state.threadId);
  if (!state.threadId) {
    showConversation({ chat: [], thread_id: "", title: "Chat" });
    renderInspect(null);
    renderHistory();
    return;
  }
  showConversation(await api(`/api/product/conversation?thread_id=${encodeURIComponent(state.threadId)}`));
  await loadThreads();
  await loadSession(state.threadId);
}

async function send(event) {
  event.preventDefault();
  const box = document.querySelector("[data-message]");
  const text = box.value.trim();
  if (!text) {
    box.focus();
    return;
  }
  const sendBtn = document.querySelector("[data-send]");
  sendBtn.disabled = true;
  const pendingItem = {
    ...(state.latest || {}),
    thread_id: state.threadId,
    chat: [
      ...((state.latest && state.latest.chat) || []),
      { role: "human", kind: "message", content: text },
    ],
  };
  showItem(pendingItem, true);
  try {
    const payload = { channel: "web", text };
    if (state.threadId) payload.thread_id = state.threadId;
    showItem(await api("/api/product/ingest", payload));
    box.value = "";
    await loadThreads();
    await loadSession(state.threadId);
  } catch (err) {
    document.querySelector("[data-product-error]").textContent = err.message || String(err);
    showItem(state.latest);
  } finally {
    sendBtn.disabled = false;
    syncButtons(state.latest);
  }
}

async function boot() {
  document.querySelector("[data-product-composer]").addEventListener("submit", send);
  document.querySelector("[data-new-chat]").addEventListener("click", async () => {
    const created = await api("/api/product/threads", { channel: "web" });
    await loadThreads();
    await pickup(created.thread_id);
    document.querySelector("[data-message]").focus();
  });
  document.querySelector("[data-approve]").addEventListener("click", async () => {
    if (!state.latest) return;
    await api(`/api/product/items/${state.latest.work_item_id}/approve`, {});
    await pickup(state.threadId);
  });
  document.querySelector("[data-deny]").addEventListener("click", async () => {
    if (!state.latest) return;
    await api(`/api/product/items/${state.latest.work_item_id}/deny`, {});
    await pickup(state.threadId);
  });
  document.querySelector("[data-resume]").addEventListener("click", async () => {
    if (!state.latest) return;
    showItem(await api(`/api/product/items/${state.latest.work_item_id}/resume`, {}));
    await loadThreads();
    await loadSession(state.threadId);
  });
  await loadThreads();
  const fromHash = threadFromHash();
  if (fromHash) {
    await pickup(fromHash);
    return;
  }
  if (state.threads.length) {
    await pickup(state.threads[0].thread_id);
    return;
  }
  showConversation(await api("/api/product/conversation?channel=web"));
}

boot();
