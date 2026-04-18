// Notebook view — NotebookLM-style 3-column layout with a Claude Code
// coordinator in the center. Loaded lazily by app.js when the Notebook tab
// is first opened.

const STATE = {
  runId: null,
  fileTree: null,
  paperPreview: null,
  projectBrief: null,
  sessionId: null,
  currentStream: null, // AbortController for the active SSE fetch
  viewer: {
    relPath: null,
    kind: null,
  },
};

const el = {};

function cacheElements() {
  if (el.form) return;
  el.form = document.getElementById("notebook-form");
  el.input = document.getElementById("notebook-input");
  el.sendButton = document.getElementById("notebook-send-button");
  el.statusChip = document.getElementById("notebook-status-chip");
  el.resetButton = document.getElementById("notebook-reset-button");
  el.events = document.getElementById("notebook-events");
  el.sources = document.getElementById("notebook-sources-body");
  el.projectTitle = document.getElementById("notebook-project-title");
  el.viewerTitle = document.getElementById("notebook-viewer-title");
  el.viewerMeta = document.getElementById("notebook-viewer-meta");
  el.viewerPath = document.getElementById("notebook-viewer-path");
  el.viewerBody = document.getElementById("notebook-viewer-body");

  el.form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    void sendMessage();
  });
  el.input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      void sendMessage();
    }
  });
  el.sendButton.addEventListener("click", (ev) => {
    if (STATE.currentStream) {
      ev.preventDefault();
      STATE.currentStream.abort();
      STATE.currentStream = null;
      setStatus("idle");
    }
  });
  el.resetButton.addEventListener("click", () => void resetSession());
}

export async function openNotebook(ctx) {
  cacheElements();
  STATE.runId = ctx.runId || null;
  STATE.fileTree = ctx.fileTree || null;
  STATE.paperPreview = ctx.paperPreview || null;
  STATE.projectBrief = ctx.projectBrief || null;
  renderSources(ctx.summary);
  if (STATE.runId) {
    await loadTranscript();
  } else {
    el.events.innerHTML = "";
    el.sources.innerHTML = '<div class="empty-state">Pick a run to populate sources.</div>';
  }
}

export function refreshSources(ctx) {
  cacheElements();
  renderSources(ctx?.summary);
}

async function loadTranscript() {
  try {
    const res = await fetch(
      `/api/notebook/transcript?run_id=${encodeURIComponent(STATE.runId)}`
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    STATE.sessionId = data.session_id || null;
    el.events.innerHTML = "";
    for (const event of data.events || []) {
      renderEvent(event, { skipTranscript: true });
    }
    scrollEventsToEnd();
  } catch (err) {
    console.warn("Notebook transcript load failed", err);
  }
}

async function resetSession() {
  if (!STATE.runId) return;
  if (!confirm("Start a fresh Claude Code session? The conversation history for this run will be cleared.")) {
    return;
  }
  try {
    await fetch("/api/notebook/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: STATE.runId }),
    });
    STATE.sessionId = null;
    el.events.innerHTML = "";
  } catch (err) {
    console.warn("Notebook reset failed", err);
  }
}

function setStatus(kind, text) {
  el.statusChip.className = `status-chip status-${kind}`;
  el.statusChip.textContent = text || (
    kind === "running" ? "Running" : kind === "error" ? "Error" : "Idle"
  );
  el.sendButton.textContent = kind === "running" ? "Stop" : "Send";
}

async function sendMessage() {
  const message = el.input.value.trim();
  if (!message) return;
  if (!STATE.runId) {
    alert("Pick a run before starting a Notebook conversation.");
    return;
  }
  if (STATE.currentStream) return; // Already running; click Stop to cancel.

  el.input.value = "";
  setStatus("running");

  const controller = new AbortController();
  STATE.currentStream = controller;

  try {
    const res = await fetch("/api/notebook/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: STATE.runId, message }),
      signal: controller.signal,
    });
    if (!res.ok || !res.body) {
      throw new Error(`HTTP ${res.status}`);
    }
    await consumeSSE(res.body, controller.signal);
  } catch (err) {
    if (err.name !== "AbortError") {
      console.warn("Notebook stream failed", err);
      renderEvent({ type: "error_chunk", detail: String(err.message || err) }, {});
      setStatus("error");
      return;
    }
  } finally {
    if (STATE.currentStream === controller) {
      STATE.currentStream = null;
    }
  }
  setStatus("idle");
}

async function consumeSSE(body, signal) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    if (signal.aborted) break;
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const lines = chunk.split("\n").filter((l) => l.startsWith("data:"));
      if (!lines.length) continue;
      const payload = lines.map((l) => l.slice(5).trim()).join("");
      if (!payload) continue;
      let parsed;
      try {
        parsed = JSON.parse(payload);
      } catch {
        continue;
      }
      handleSSE(parsed);
    }
  }
}

function handleSSE(envelope) {
  if (envelope.type === "done") {
    setStatus("idle");
    return;
  }
  if (envelope.type === "error") {
    renderEvent({ type: "error_chunk", detail: envelope.detail }, {});
    setStatus("error");
    return;
  }
  if (envelope.type === "event") {
    renderEvent(envelope.data, {});
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function scrollEventsToEnd() {
  el.events.scrollTop = el.events.scrollHeight;
}

function renderEvent(event, opts) {
  const block = buildEventBlock(event);
  if (!block) return;
  el.events.appendChild(block);
  scrollEventsToEnd();
}

function buildEventBlock(event) {
  // Our own echo of the user's typed message.
  if (event.type === "user_echo") {
    return userBubble(event.text || "");
  }

  // Transcript-persisted user event saved by the backend.
  if (event.type === "user" && typeof event.text === "string") {
    return userBubble(event.text);
  }

  // Full claude CLI event. The shape is { type, message: {content: [...]}, ... }
  if (event.type === "assistant") {
    return assistantBlock(event);
  }

  if (event.type === "result") {
    return resultBlock(event);
  }

  if (event.type === "system" && event.subtype === "init") {
    return initBlock(event);
  }

  // All other system events (hook_started, hook_response, etc.) are noisy —
  // CC emits many of them per request. We drop them from the visible chat
  // but they're still persisted to the transcript.jsonl for debugging.
  if (event.type === "system") {
    return null;
  }

  if (event.type === "user" && event.message && typeof event.message === "object") {
    // tool_result / stdin echo from claude. We collapse these.
    return toolResultBlock(event);
  }

  if (event.type === "error_chunk") {
    return errorBlock(event.detail || "Unknown error");
  }

  return null;
}

function userBubble(text) {
  const div = document.createElement("li");
  div.className = "notebook-event notebook-event-user";
  const body = document.createElement("div");
  body.className = "notebook-bubble notebook-bubble-user";
  body.textContent = text;
  div.appendChild(body);
  return div;
}

function assistantBlock(event) {
  const wrapper = document.createElement("li");
  wrapper.className = "notebook-event notebook-event-assistant";
  const content = event.message?.content || [];
  for (const item of content) {
    if (item.type === "text" && item.text) {
      const node = document.createElement("div");
      node.className = "notebook-assistant-text";
      node.innerHTML = renderMarkdown(item.text);
      wrapper.appendChild(node);
    } else if (item.type === "thinking" && item.thinking) {
      const details = document.createElement("details");
      details.className = "notebook-thinking";
      const summary = document.createElement("summary");
      summary.textContent = "Thinking…";
      details.appendChild(summary);
      const pre = document.createElement("pre");
      pre.textContent = item.thinking;
      details.appendChild(pre);
      wrapper.appendChild(details);
    } else if (item.type === "tool_use") {
      wrapper.appendChild(toolUseChip(item));
    }
  }
  return wrapper.childNodes.length ? wrapper : null;
}

function toolUseChip(tool) {
  const chip = document.createElement("div");
  chip.className = "notebook-tool-chip";
  const name = tool.name || "tool";
  const input = tool.input || {};
  const target = pickToolTarget(name, input);
  const pretty = prettyToolLabel(name, input);

  const head = document.createElement("div");
  head.className = "notebook-tool-head";
  head.innerHTML = `
    <span class="notebook-tool-name">${escapeHtml(name)}</span>
    <span class="notebook-tool-target">${escapeHtml(pretty)}</span>
  `;
  chip.appendChild(head);

  // Clickable target: open in the viewer if it looks like a workspace file.
  if (target && isLikelyFile(target)) {
    chip.classList.add("notebook-tool-clickable");
    chip.addEventListener("click", () => openInViewer(target));
    chip.title = `Open ${target} in viewer`;
  }

  return chip;
}

function pickToolTarget(name, input) {
  if (!input || typeof input !== "object") return null;
  if (typeof input.file_path === "string") return input.file_path;
  if (typeof input.path === "string") return input.path;
  if (typeof input.notebook_path === "string") return input.notebook_path;
  if (typeof input.pattern === "string") return input.pattern;
  if (typeof input.command === "string") return input.command;
  return null;
}

function prettyToolLabel(name, input) {
  const target = pickToolTarget(name, input);
  if (!target) return "";
  if (name === "Bash") {
    return target.length > 120 ? target.slice(0, 117) + "…" : target;
  }
  return target;
}

function isLikelyFile(target) {
  if (!target || target.includes("\n")) return false;
  if (target.startsWith("/")) return true;
  if (/\.[a-zA-Z0-9]+$/.test(target)) return true;
  return false;
}

function toolResultBlock(event) {
  const items = event.message?.content || [];
  const texts = items
    .filter((c) => c.type === "tool_result" && typeof c.content === "string")
    .map((c) => c.content);
  if (!texts.length) return null;
  const li = document.createElement("li");
  li.className = "notebook-event notebook-event-tool-result";
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Tool result";
  details.appendChild(summary);
  const pre = document.createElement("pre");
  pre.textContent = texts.join("\n---\n");
  details.appendChild(pre);
  li.appendChild(details);
  return li;
}

function resultBlock(event) {
  const li = document.createElement("li");
  li.className = "notebook-event notebook-event-result";
  const meta = document.createElement("div");
  meta.className = "notebook-meta-line";
  const dur = typeof event.duration_ms === "number" ? ` · ${Math.round(event.duration_ms / 100) / 10}s` : "";
  const cost = typeof event.total_cost_usd === "number" ? ` · $${event.total_cost_usd.toFixed(4)}` : "";
  meta.textContent = `✓ done${dur}${cost}`;
  li.appendChild(meta);
  return li;
}

function initBlock(event) {
  const li = document.createElement("li");
  li.className = "notebook-event notebook-event-init";
  li.textContent = `Session ${event.session_id?.slice(0, 8) || "started"}`;
  return li;
}

function errorBlock(detail) {
  const li = document.createElement("li");
  li.className = "notebook-event notebook-event-error";
  li.textContent = detail;
  return li;
}

// ---------------------------------------------------------------------------
// Left rail
// ---------------------------------------------------------------------------

function renderSources(summary) {
  if (!el.sources) return;
  if (!STATE.runId) {
    el.sources.innerHTML = '<div class="empty-state">Pick a run to populate sources.</div>';
    return;
  }
  el.projectTitle.textContent = STATE.projectBrief?.title || "Project";
  const sections = [];
  sections.push(sourceSection("Project", renderProjectSection()));
  sections.push(sourceSection("Run", renderRunSection(summary)));
  sections.push(sourceSection("Stages", renderStagesSection(summary)));
  sections.push(sourceSection("Workspace", renderWorkspaceSection()));
  sections.push(sourceSection("Paper", renderPaperSection()));
  el.sources.innerHTML = "";
  for (const section of sections) {
    el.sources.appendChild(section);
  }
}

function sourceSection(label, bodyNode) {
  const details = document.createElement("details");
  details.className = "notebook-source-section";
  details.open = true;
  const summary = document.createElement("summary");
  summary.textContent = label;
  details.appendChild(summary);
  details.appendChild(bodyNode);
  return details;
}

function renderProjectSection() {
  const wrap = document.createElement("div");
  wrap.className = "notebook-source-body";
  const thesis = STATE.projectBrief?.thesis || "(no thesis)";
  const title = STATE.projectBrief?.title || "(untitled)";
  wrap.innerHTML = `
    <p class="notebook-source-title">${escapeHtml(title)}</p>
    <p class="notebook-source-thesis">${escapeHtml(thesis)}</p>
  `;
  return wrap;
}

function renderRunSection(summary) {
  const wrap = document.createElement("div");
  wrap.className = "notebook-source-body";
  if (!summary) {
    wrap.innerHTML = `<p class="notebook-source-thesis">Run id: ${escapeHtml(STATE.runId)}</p>`;
    return wrap;
  }
  wrap.innerHTML = `
    <dl class="notebook-source-dl">
      <div><dt>Run id</dt><dd>${escapeHtml(summary.run_id)}</dd></div>
      <div><dt>Status</dt><dd>${escapeHtml(summary.run_status || "unknown")}</dd></div>
      <div><dt>Focus</dt><dd>${escapeHtml(summary.current_stage_slug || "—")}</dd></div>
      <div><dt>Artifacts</dt><dd>${escapeHtml(String(summary.artifact_count || 0))}</dd></div>
    </dl>
  `;
  return wrap;
}

function renderStagesSection(summary) {
  const wrap = document.createElement("div");
  wrap.className = "notebook-source-body";
  const stages = summary?.stages || [];
  if (!stages.length) {
    wrap.innerHTML = '<p class="empty-state">No stages yet.</p>';
    return wrap;
  }
  const list = document.createElement("ul");
  list.className = "notebook-source-list";
  for (const stage of stages) {
    const li = document.createElement("li");
    li.className = `notebook-stage-row notebook-status-${stage.status || "pending"}`;
    li.innerHTML = `
      <span class="notebook-status-dot"></span>
      <span class="notebook-stage-label">${escapeHtml(String(stage.number || ""))}. ${escapeHtml(stage.title || stage.slug)}</span>
      <span class="notebook-stage-status">${escapeHtml(stage.status || "pending")}</span>
    `;
    li.addEventListener("click", () => openStageInViewer(stage.slug, stage.title));
    list.appendChild(li);
  }
  wrap.appendChild(list);
  return wrap;
}

function renderWorkspaceSection() {
  const wrap = document.createElement("div");
  wrap.className = "notebook-source-body notebook-tree";
  if (!STATE.fileTree) {
    wrap.innerHTML = '<p class="empty-state">No workspace tree loaded.</p>';
    return wrap;
  }
  wrap.appendChild(renderTreeNode(STATE.fileTree));
  return wrap;
}

function renderTreeNode(node) {
  const root = document.createElement("div");
  root.className = "notebook-tree-node";
  if (node.kind === "directory") {
    const details = document.createElement("details");
    details.open = node.depth === 0;
    const summary = document.createElement("summary");
    summary.textContent = node.name || "workspace";
    details.appendChild(summary);
    const list = document.createElement("div");
    list.className = "notebook-tree-children";
    for (const child of node.children || []) {
      list.appendChild(renderTreeNode(child));
    }
    details.appendChild(list);
    root.appendChild(details);
  } else {
    const label = document.createElement("div");
    label.className = "notebook-tree-file";
    label.textContent = node.name;
    label.title = node.rel_path;
    label.addEventListener("click", () => openInViewer(node.rel_path, { isRunRelative: true }));
    root.appendChild(label);
  }
  return root;
}

function renderPaperSection() {
  const wrap = document.createElement("div");
  wrap.className = "notebook-source-body";
  const preview = STATE.paperPreview;
  if (!preview) {
    wrap.innerHTML = '<p class="empty-state">No paper artifacts yet.</p>';
    return wrap;
  }
  const list = document.createElement("ul");
  list.className = "notebook-source-list";
  if (preview.tex_relative_path) {
    list.appendChild(paperLink("Main TeX", preview.tex_relative_path));
  }
  if (preview.pdf_relative_path) {
    list.appendChild(paperLink("PDF", preview.pdf_relative_path));
  }
  if (preview.build_log_relative_path) {
    list.appendChild(paperLink("Build log", preview.build_log_relative_path));
  }
  for (const section of preview.section_paths || []) {
    list.appendChild(paperLink(section.split("/").pop(), section));
  }
  if (!list.childNodes.length) {
    wrap.innerHTML = '<p class="empty-state">No paper artifacts yet.</p>';
  } else {
    wrap.appendChild(list);
  }
  return wrap;
}

function paperLink(label, relPath) {
  const li = document.createElement("li");
  li.className = "notebook-paper-link";
  li.innerHTML = `<span>${escapeHtml(label)}</span><span class="meta">${escapeHtml(relPath)}</span>`;
  li.addEventListener("click", () => openInViewer(relPath, { isRunRelative: true }));
  return li;
}

// ---------------------------------------------------------------------------
// Viewer
// ---------------------------------------------------------------------------

function openStageInViewer(slug, title) {
  if (!STATE.runId || !slug) return;
  el.viewerTitle.textContent = title || slug;
  el.viewerPath.textContent = `stages/${slug}.md`;
  el.viewerMeta.textContent = "stage summary";
  el.viewerBody.classList.add("notebook-viewer-loading");
  el.viewerBody.textContent = "Loading…";
  fetch(`/api/runs/${STATE.runId}/stages/${slug}`)
    .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
    .then((payload) => {
      el.viewerBody.classList.remove("notebook-viewer-loading", "empty-state");
      el.viewerBody.innerHTML = renderMarkdown(payload.markdown || "*Stage summary is empty.*");
    })
    .catch((err) => {
      el.viewerBody.classList.remove("notebook-viewer-loading");
      el.viewerBody.classList.add("empty-state");
      el.viewerBody.textContent = `Failed to load stage: ${err}`;
    });
}

function openInViewer(relPath, opts) {
  if (!STATE.runId || !relPath) return;
  const ext = extensionOf(relPath);
  el.viewerTitle.textContent = relPath.split("/").pop();
  el.viewerPath.textContent = relPath;
  el.viewerMeta.textContent = ext.slice(1).toUpperCase() || "file";
  el.viewerBody.classList.remove("empty-state");

  if (ext === ".pdf") {
    el.viewerBody.innerHTML = `<iframe class="notebook-pdf-frame" src="/api/runs/${encodeURIComponent(STATE.runId)}/paper/pdf" title="PDF"></iframe>`;
    el.viewerMeta.textContent = "PDF";
    return;
  }
  if ([".png", ".jpg", ".jpeg", ".gif", ".svg"].includes(ext)) {
    el.viewerBody.innerHTML = "";
    const img = document.createElement("img");
    img.className = "notebook-image";
    img.src = `/api/runs/${encodeURIComponent(STATE.runId)}/files/content?path=${encodeURIComponent(relPath)}&as=raw`;
    img.alt = relPath;
    el.viewerBody.appendChild(img);
    return;
  }

  el.viewerBody.classList.add("notebook-viewer-loading");
  el.viewerBody.textContent = "Loading…";
  fetch(`/api/runs/${encodeURIComponent(STATE.runId)}/files/content?path=${encodeURIComponent(relPath)}`)
    .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
    .then((payload) => {
      el.viewerBody.classList.remove("notebook-viewer-loading");
      if (payload.encoding === "binary") {
        el.viewerBody.classList.add("empty-state");
        el.viewerBody.textContent = "Binary file preview is unavailable.";
        return;
      }
      if (ext === ".md" || ext === ".markdown") {
        el.viewerBody.innerHTML = renderMarkdown(payload.content || "");
        return;
      }
      const pre = document.createElement("pre");
      pre.className = "notebook-code";
      pre.textContent = payload.content || "";
      el.viewerBody.innerHTML = "";
      el.viewerBody.appendChild(pre);
    })
    .catch((err) => {
      el.viewerBody.classList.remove("notebook-viewer-loading");
      el.viewerBody.classList.add("empty-state");
      el.viewerBody.textContent = `Failed to load: ${err}`;
    });
}

function extensionOf(path) {
  const match = /\.[a-zA-Z0-9]+$/.exec(path);
  return match ? match[0].toLowerCase() : "";
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderMarkdown(source) {
  // Light markdown: headings, paragraphs, fenced code, inline code, links,
  // bold, italic, lists. Good enough for stage summaries and CC output.
  if (!source) return "";
  const lines = source.split("\n");
  const out = [];
  let inCode = false;
  let codeBuf = [];
  let inList = false;
  const flushList = () => {
    if (inList) {
      out.push("</ul>");
      inList = false;
    }
  };
  for (const raw of lines) {
    if (raw.startsWith("```")) {
      if (inCode) {
        out.push(`<pre class="notebook-code">${escapeHtml(codeBuf.join("\n"))}</pre>`);
        codeBuf = [];
        inCode = false;
      } else {
        flushList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(raw);
      continue;
    }
    if (/^#{1,6}\s/.test(raw)) {
      flushList();
      const level = raw.match(/^#+/)[0].length;
      out.push(`<h${level}>${inline(raw.slice(level + 1))}</h${level}>`);
      continue;
    }
    if (/^\s*[-*]\s+/.test(raw)) {
      if (!inList) {
        out.push("<ul>");
        inList = true;
      }
      out.push(`<li>${inline(raw.replace(/^\s*[-*]\s+/, ""))}</li>`);
      continue;
    }
    if (!raw.trim()) {
      flushList();
      continue;
    }
    flushList();
    out.push(`<p>${inline(raw)}</p>`);
  }
  if (inCode) {
    out.push(`<pre class="notebook-code">${escapeHtml(codeBuf.join("\n"))}</pre>`);
  }
  flushList();
  return out.join("\n");
}

function inline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, label, href) => {
      if (/^https?:/.test(href)) {
        return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener">${label}</a>`;
      }
      return `<a href="#" data-notebook-rel="${escapeHtml(href)}">${label}</a>`;
    });
}
