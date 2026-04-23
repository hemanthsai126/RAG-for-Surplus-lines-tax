/**
 * CDN scripts (`marked`, `dompurify`) attach to `window`. This file is `type="module"`,
 * so those globals are NOT visible as bare identifiers — use `globalThis` or links never render.
 */
const markedLib = globalThis.marked;
const domPurifyLib = globalThis.DOMPurify;

const chatEl = document.getElementById("chat");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const statusEl = document.getElementById("status");
const ingestBtn = document.getElementById("ingestBtn");
const scrollDownBtn = document.getElementById("scrollDownBtn");
const bottomDock = document.getElementById("bottomDock");
const appEl = document.querySelector(".app");

const SCROLL_BOTTOM_THRESHOLD_PX = 96;

/** While true, assistant stream auto-scrolls (user has not scrolled up). */
let streamStickToBottom = true;

/** @type {{role: string, content: string}[]} */
let history = [];

/**
 * Wrap bare http(s) URLs in markdown [url](url) so marked emits <a href>.
 * Skips fenced code, inline code, and existing markdown links.
 * @param {string} md
 */
function autolinkUrlsInMarkdown(md) {
  const saved = [];
  const hide = (m) => {
    saved.push(m);
    return `\x00S${saved.length - 1}\x00`;
  };
  let s = md;
  s = s.replace(/```[\s\S]*?```/g, hide);
  s = s.replace(/`[^`\n]+`/g, hide);
  s = s.replace(/\[([^\]]*)\]\(([^)]*)\)/g, hide);

  /* Lead char before URL: start, whitespace, `(`, `>`, or `<` (e.g. `<https://...>`). */
  s = s.replace(/(^|[\s(><])((?:https?:\/\/)[^\s<>\[\]()'"]+)/gim, (match, lead, url) => {
    let u = url;
    u = u.replace(/[),.;:!?]+$/g, "");
    const tail = url.slice(u.length);
    return `${lead}[${u}](${u})${tail}`;
  });

  s = s.replace(/\x00S(\d+)\x00/g, (_, i) => saved[Number(i)]);
  return s;
}

/**
 * Open external statute / doc links in a new tab safely.
 * @param {string} html
 */
function addExternalLinkAttrs(html) {
  let out = html.replace(/<a\s+href="(https?:[^"]+)"/gi, (m, href) => {
    if (/target\s*=/i.test(m)) return m;
    return `<a target="_blank" rel="noopener noreferrer" href="${href}"`;
  });
  out = out.replace(/<a\s+href='(https?:[^']+)'/gi, (m, href) => {
    if (/target\s*=/i.test(m)) return m;
    return `<a target="_blank" rel="noopener noreferrer" href="${href}"`;
  });
  return out;
}

/** @param {string} md @returns {string | null} */
function parseMarkdown(md) {
  if (!markedLib) return null;
  if (typeof markedLib.parse === "function") {
    return markedLib.parse(md);
  }
  if (typeof markedLib === "function") {
    return markedLib(md);
  }
  return null;
}

/**
 * Render assistant text as Markdown (tables, **bold**, lists). Safe HTML via DOMPurify.
 * @param {string} text
 */
function renderAssistantMarkdown(text) {
  if (!markedLib || !domPurifyLib) {
    const esc = document.createElement("div");
    esc.textContent = text;
    return `<div class="md-body md-fallback">${esc.innerHTML}</div>`;
  }
  markedLib.setOptions?.({ gfm: true, breaks: true });
  const withLinks = autolinkUrlsInMarkdown(text);
  const raw = parseMarkdown(withLinks);
  if (raw == null) {
    const esc = document.createElement("div");
    esc.textContent = text;
    return `<div class="md-body md-fallback">${esc.innerHTML}</div>`;
  }
  let clean = domPurifyLib.sanitize(raw, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ["target", "rel"],
  });
  clean = addExternalLinkAttrs(clean);
  clean = clean.replace(/<table[\s\S]*?<\/table>/gi, (m) => `<div class="table-wrap">${m}</div>`);
  return `<div class="md-body">${clean}</div>`;
}

function formatHttpDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((x) => (typeof x === "object" && x.msg ? x.msg : JSON.stringify(x))).join("; ");
  return detail ? String(detail) : "";
}

async function refreshHealth() {
  try {
    const r = await fetch("/api/health");
    const d = await r.json();
    const roots =
      Array.isArray(d.pdfs_dirs) && d.pdfs_dirs.length
        ? d.pdfs_dirs.join(", ")
        : d.pdfs_dir || "";
    const pdfHint = roots ? ` · PDF folders: ${roots}` : "";
    if (d.indexed && d.chunks > 0) {
      statusEl.textContent = `Indexed · ${d.chunks} chunks`;
      statusEl.className = "pill ok";
    } else {
      statusEl.textContent = `No index — click Re-index below${pdfHint}`;
      statusEl.className = "pill warn";
    }
  } catch {
    statusEl.textContent = "API unreachable";
    statusEl.className = "pill warn";
  }
}

function isChatNearBottom() {
  return (
    chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < SCROLL_BOTTOM_THRESHOLD_PX
  );
}

function updateScrollDownButton() {
  if (!scrollDownBtn || !chatEl) return;
  if (isChatNearBottom()) {
    scrollDownBtn.classList.remove("visible");
  } else {
    scrollDownBtn.classList.add("visible");
  }
}

function syncBottomDockPadding() {
  if (!bottomDock || !appEl) return;
  const h = Math.ceil(bottomDock.getBoundingClientRect().height);
  appEl.style.setProperty("--dock-reserved", `${h + 16}px`);
}

function scrollChatToBottom(smooth = false) {
  if (!chatEl) return;
  const target = chatEl.scrollHeight;
  chatEl.scrollTo({
    top: target,
    behavior: smooth ? "smooth" : "auto",
  });
  requestAnimationFrame(() => {
    chatEl.scrollTop = chatEl.scrollHeight;
    requestAnimationFrame(() => {
      chatEl.scrollTop = chatEl.scrollHeight;
      updateScrollDownButton();
    });
  });
}

if (scrollDownBtn) {
  scrollDownBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    scrollChatToBottom(true);
  });
}

if (bottomDock && appEl && typeof ResizeObserver !== "undefined") {
  const ro = new ResizeObserver(() => syncBottomDockPadding());
  ro.observe(bottomDock);
} else {
  window.addEventListener("resize", syncBottomDockPadding);
}
syncBottomDockPadding();

chatEl.addEventListener("scroll", () => {
  streamStickToBottom = isChatNearBottom();
  updateScrollDownButton();
});

function appendMessage(role, text, streaming = false) {
  const div = document.createElement("div");
  div.className = `msg ${role}${streaming ? " assistant cursor" : ""}`;
  div.textContent = text;
  chatEl.appendChild(div);
  const stick = isChatNearBottom() || role === "user";
  if (stick) {
    scrollChatToBottom(false);
  } else {
    updateScrollDownButton();
  }
  return div;
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;
  streamStickToBottom = true;
  inputEl.value = "";
  appendMessage("user", text);
  history.push({ role: "user", content: text });

  const bubble = appendMessage("assistant", "", true);

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: history.slice(0, -1) }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      bubble.classList.remove("cursor");
      bubble.textContent =
        formatHttpDetail(err.detail) || res.statusText || "Request failed";
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let full = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (!payload) continue;
        try {
          const data = JSON.parse(payload);
          if (data.error) {
            bubble.classList.remove("cursor");
            bubble.textContent = data.error;
            return;
          }
          if (data.token) {
            full += data.token;
            bubble.textContent = full;
            if (streamStickToBottom) {
              scrollChatToBottom(false);
            } else {
              updateScrollDownButton();
            }
          }
          if (data.done) break;
        } catch {
          /* ignore partial */
        }
      }
    }
    bubble.classList.remove("cursor");
    bubble.innerHTML = renderAssistantMarkdown(full);
    history.push({ role: "assistant", content: full });
    if (streamStickToBottom || isChatNearBottom()) {
      scrollChatToBottom(false);
    }
    updateScrollDownButton();
  } catch (e) {
    bubble.classList.remove("cursor");
    bubble.textContent = String(e);
  }
}

sendBtn.addEventListener("click", sendMessage);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

if (inputEl) {
  inputEl.addEventListener("input", syncBottomDockPadding);
}

ingestBtn.addEventListener("click", async () => {
  ingestBtn.disabled = true;
  statusEl.textContent = "Indexing…";
  statusEl.className = "pill muted";
  try {
    const r = await fetch("/api/ingest", { method: "POST" });
    const d = await r.json().catch(() => ({}));
    if (r.ok && d.ok) {
      const n = d.sources ?? d.pdfs;
      statusEl.textContent = `Indexed ${d.chunks} chunks from ${n} source file(s)`;
      statusEl.className = "pill ok";
    } else {
      statusEl.textContent =
        d.message ||
        formatHttpDetail(d.detail) ||
        (r.status >= 400 ? `HTTP ${r.status}` : "") ||
        "Ingest failed — check PDF folder and server logs";
      statusEl.className = "pill warn";
    }
  } catch (e) {
    statusEl.textContent = String(e);
    statusEl.className = "pill warn";
  }
  ingestBtn.disabled = false;
  await refreshHealth();
  syncBottomDockPadding();
  updateScrollDownButton();
});

refreshHealth();
syncBottomDockPadding();
updateScrollDownButton();
