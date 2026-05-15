/**
 * static/js/app.js
 * Agent Factory — Chat UI JavaScript
 * PROJ-142 (Dilraj Singh) — updated PROJ-191 (new UI + Integrity + Seller tabs)
 */

const API_BASE = "";

/* ── DOM refs ─────────────────────────────────────────────── */
const statusDot    = document.getElementById("status-dot");
const statusLabel  = document.getElementById("status-label");
const historyList  = document.getElementById("history-list");

// Chat tab
const chatArea     = document.getElementById("chat-area");
const chatWelcome  = document.getElementById("chat-welcome");
const queryInput   = document.getElementById("query-input");
const sendBtn      = document.getElementById("send-btn");

// Research tab
const researchArea  = document.getElementById("research-area");
const researchInput = document.getElementById("research-input");
const researchBtn   = document.getElementById("research-btn");

// Shopping tab
const shoppingArea  = document.getElementById("shopping-area");
const shoppingInput = document.getElementById("shopping-input");
const shoppingBtn   = document.getElementById("shopping-btn");

// Integrity tab
const integrityArea  = document.getElementById("integrity-area");
const integrityInput = document.getElementById("integrity-input");
const integrityBtn   = document.getElementById("integrity-btn");

let isLoading = false;
let activeTab = "chat";

/* ══════════════════════════════════════════════════════════
   INIT
══════════════════════════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", () => {
  checkStatus();
  loadHistory();

  // Nav tab switching
  document.querySelectorAll(".nav-item[data-tab]").forEach(item => {
    item.addEventListener("click", () => switchTab(item.dataset.tab));
  });

  // Chat input
  queryInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
  });
  queryInput.addEventListener("input", () => autoResize(queryInput));
  sendBtn.addEventListener("click", sendChatMessage);

  // Research input
  researchInput.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); sendResearchQuery(); }
  });
  researchBtn.addEventListener("click", sendResearchQuery);

  // Shopping input
  shoppingInput.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); sendShoppingQuery(); }
  });
  shoppingBtn.addEventListener("click", sendShoppingQuery);

  // Integrity input — Ctrl+Enter or button
  integrityInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); sendIntegrityCheck(); }
  });
  integrityBtn.addEventListener("click", sendIntegrityCheck);
});

/* ══════════════════════════════════════════════════════════
   TAB SWITCHING
══════════════════════════════════════════════════════════ */
function switchTab(tabName) {
  // Update nav
  document.querySelectorAll(".nav-item[data-tab]").forEach(item => {
    item.classList.toggle("active", item.dataset.tab === tabName);
  });
  // Show/hide panels
  document.querySelectorAll(".tab-panel").forEach(panel => {
    panel.classList.toggle("active", panel.id === `tab-${tabName}`);
  });
  activeTab = tabName;
}

/* ══════════════════════════════════════════════════════════
   STATUS CHECK
══════════════════════════════════════════════════════════ */
async function checkStatus() {
  try {
    const res  = await fetch(`${API_BASE}/status`);
    const data = await res.json();
    const ok   = data.status === "ok";
    statusDot.classList.toggle("offline", !ok);
    statusLabel.textContent = ok ? "Online · v2.0.0" : "Agent error";
  } catch {
    statusDot.classList.add("offline");
    statusLabel.textContent = "Offline";
  }
}

/* ══════════════════════════════════════════════════════════
   HISTORY
══════════════════════════════════════════════════════════ */
async function loadHistory() {
  try {
    const res = await fetch(`${API_BASE}/history`);
    if (!res.ok) return;
    const history = await res.json();
    if (!history || history.length === 0) return;

    historyList.innerHTML = "";
    history.slice(-8).reverse().forEach(item => {
      const el = document.createElement("div");
      el.className = "hist-item";
      el.innerHTML = `<span class="hist-icon">⏱</span>${escHtml(item.query || "")}`;
      el.title = item.query || "";
      el.onclick = () => {
        switchTab("chat");
        queryInput.value = item.query || "";
        autoResize(queryInput);
        queryInput.focus();
      };
      historyList.appendChild(el);
    });
  } catch { /* silently ignore */ }
}

/* ══════════════════════════════════════════════════════════
   CHAT TAB
══════════════════════════════════════════════════════════ */
async function sendChatMessage() {
  const query = queryInput.value.trim();
  if (!query || isLoading) return;

  hideWelcome();
  appendChatBubble(query, "user");
  queryInput.value = "";
  autoResize(queryInput);
  setLoading(true, sendBtn, queryInput);

  const typingId = showTyping(chatArea);
  try {
    const res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    removeTyping(typingId);

    const cards = data.cards || [];
    appendAgentBubble(chatArea, data.response || "", cards, data.type || "");
    loadHistory(); // refresh sidebar history
  } catch (err) {
    removeTyping(typingId);
    appendChatBubble(`Sorry, something went wrong: ${err.message}`, "error");
  } finally {
    setLoading(false, sendBtn, queryInput);
    scrollToBottom(chatArea);
  }
}

function hideWelcome() {
  if (chatWelcome) chatWelcome.style.display = "none";
}

function appendChatBubble(text, type) {
  if (type === "user") {
    const row = document.createElement("div");
    row.className = "msg-row user";
    row.innerHTML = `
      <div class="msg-content" style="display:flex;flex-direction:column;align-items:flex-end;">
        <div class="msg-name" style="justify-content:flex-end;">You</div>
        <div class="user-bubble">${escHtml(text)}</div>
      </div>
      <div class="avatar user-av">Y</div>`;
    chatArea.appendChild(row);
  } else {
    const row = document.createElement("div");
    row.className = "msg-row";
    const cls = type === "error" ? "error-bubble" : "ai-bubble";
    row.innerHTML = `
      ${aiAvatarHtml()}
      <div class="msg-content">
        <div class="msg-name">Agent Factory</div>
        <div class="${cls}">${escHtml(text)}</div>
      </div>`;
    chatArea.appendChild(row);
  }
}

/* ══════════════════════════════════════════════════════════
   RESEARCH TAB — POST /literature
══════════════════════════════════════════════════════════ */
async function sendResearchQuery() {
  const query = researchInput.value.trim();
  if (!query || isLoading) return;

  appendUserMsg(researchArea, query);
  researchInput.value = "";
  setLoading(true, researchBtn, researchInput);
  const typingId = showTyping(researchArea);

  try {
    const res = await fetch(`${API_BASE}/literature`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    removeTyping(typingId);

    const cards = data.papers || data.cards || data.results || [];
    appendAgentBubble(researchArea, data.synthesis || data.response || data.summary || "", cards, "literature");
  } catch (err) {
    removeTyping(typingId);
    appendErrorMsg(researchArea, err.message);
  } finally {
    setLoading(false, researchBtn, researchInput);
    scrollToBottom(researchArea);
  }
}

/* ══════════════════════════════════════════════════════════
   SHOPPING TAB — POST /query (amazon type)
══════════════════════════════════════════════════════════ */
async function sendShoppingQuery() {
  const query = shoppingInput.value.trim();
  if (!query || isLoading) return;

  appendUserMsg(shoppingArea, query);
  shoppingInput.value = "";
  setLoading(true, shoppingBtn, shoppingInput);
  const typingId = showTyping(shoppingArea);

  try {
    const res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    removeTyping(typingId);

    // Try /seller for dedicated seller tool results
    const cards = data.cards || data.results || [];
    appendAgentBubble(shoppingArea, data.response || data.summary || "", cards, data.type || "amazon");

    // Also show supplier/campaign cards if present
    if (data.suppliers && data.suppliers.length > 0) {
      appendSupplierCards(shoppingArea, data.suppliers);
    }
    if (data.campaigns && data.campaigns.length > 0) {
      appendCampaignCards(shoppingArea, data.campaigns);
    }
  } catch (err) {
    removeTyping(typingId);
    appendErrorMsg(shoppingArea, err.message);
  } finally {
    setLoading(false, shoppingBtn, shoppingInput);
    scrollToBottom(shoppingArea);
  }
}

/* ══════════════════════════════════════════════════════════
   INTEGRITY TAB — POST /integrity
══════════════════════════════════════════════════════════ */
async function sendIntegrityCheck() {
  const text = integrityInput.value.trim();
  if (!text || isLoading) return;

  appendUserMsg(integrityArea, text.length > 100 ? text.slice(0, 100) + "…" : text);
  integrityInput.value = "";
  setLoading(true, integrityBtn, integrityInput);
  const typingId = showTyping(integrityArea);

  try {
    const res = await fetch(`${API_BASE}/integrity`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    removeTyping(typingId);

    renderIntegrityResult(integrityArea, data);
  } catch (err) {
    removeTyping(typingId);
    appendErrorMsg(integrityArea, err.message);
  } finally {
    setLoading(false, integrityBtn, integrityInput);
    scrollToBottom(integrityArea);
  }
}

/* ══════════════════════════════════════════════════════════
   RENDER HELPERS
══════════════════════════════════════════════════════════ */

/** Append an agent bubble with optional result cards. */
function appendAgentBubble(area, responseText, cards, type) {
  const row = document.createElement("div");
  row.className = "msg-row";

  let cardsHtml = "";
  if (cards && cards.length > 0) {
    cardsHtml = `<div class="cards">${cards.map(c =>
      type === "amazon" || type === "shopping" ? buildProductCard(c) : buildPaperCard(c)
    ).join("")}</div>`;
  }

  const renderedText = (typeof marked !== "undefined" && responseText)
    ? marked.parse(responseText)
    : escHtml(responseText || "");
  const summaryHtml = responseText
    ? `<div class="summary-block">
         <div class="summary-label">✦ AI Summary</div>
         <div class="summary-text md-content">${renderedText}</div>
       </div>`
    : "";

  const skillLabel = type === "amazon" ? "Shopping"
    : type === "literature" ? "Literature"
    : type === "integrity" ? "Integrity"
    : "Agent";

  row.innerHTML = `
    ${aiAvatarHtml()}
    <div class="msg-content">
      <div class="msg-name">Agent Factory <span class="skill-badge">${escHtml(skillLabel)}</span></div>
      <div class="ai-bubble">
        ${summaryHtml}
        ${cardsHtml}
      </div>
    </div>`;
  area.appendChild(row);
}

/** Append a plain user message row. */
function appendUserMsg(area, text) {
  const row = document.createElement("div");
  row.className = "msg-row user";
  row.innerHTML = `
    <div class="msg-content" style="display:flex;flex-direction:column;align-items:flex-end;">
      <div class="msg-name" style="justify-content:flex-end;">You</div>
      <div class="user-bubble">${escHtml(text)}</div>
    </div>
    <div class="avatar user-av">Y</div>`;
  area.appendChild(row);
}

/** Append an error message row. */
function appendErrorMsg(area, message) {
  const row = document.createElement("div");
  row.className = "msg-row";
  row.innerHTML = `
    ${aiAvatarHtml()}
    <div class="msg-content">
      <div class="msg-name">Agent Factory</div>
      <div class="error-bubble">Sorry, something went wrong: ${escHtml(message)}</div>
    </div>`;
  area.appendChild(row);
}

/** Render integrity check results (IntegrityCard). */
function renderIntegrityResult(area, data) {
  const row = document.createElement("div");
  row.className = "msg-row";

  // Support both flat result and nested .result
  const result = data.result || data;
  const prob   = typeof result.ai_probability === "number" ? result.ai_probability : (data.ai_probability || 0);
  const riskLevel = prob >= 0.7 ? "high" : prob >= 0.4 ? "medium" : "low";
  const riskLabel = prob >= 0.7 ? "High Risk" : prob >= 0.4 ? "Moderate Risk" : "Low Risk";
  const pct        = Math.round(prob * 100);
  const summary    = result.summary || data.response || data.summary || "";
  const details    = result.details || data.details || [];

  let detailsHtml = "";
  if (details.length > 0) {
    detailsHtml = `<ul style="margin-top:10px;padding-left:18px;font-size:13px;color:var(--text2);">${
      details.map(d => `<li>${escHtml(d)}</li>`).join("")
    }</ul>`;
  }

  row.innerHTML = `
    ${aiAvatarHtml()}
    <div class="msg-content">
      <div class="msg-name">Agent Factory <span class="skill-badge">Integrity</span></div>
      <div class="ai-bubble">
        <div class="integrity-card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
            <span style="font-size:13px;font-weight:600;color:var(--text);">AI Authorship Probability</span>
            <span class="risk-badge ${riskLevel}">${escHtml(riskLabel)}</span>
          </div>
          <div class="ai-prob-bar-wrap">
            <div class="ai-prob-bar ${riskLevel}" style="width:${pct}%;"></div>
          </div>
          <div style="font-size:12px;color:var(--text2);margin-top:4px;">${pct}% likely AI-generated</div>
          ${summary ? `<div class="summary-block" style="margin-top:12px;"><div class="summary-label">Analysis</div><div class="summary-text">${escHtml(summary)}</div></div>` : ""}
          ${detailsHtml}
        </div>
      </div>
    </div>`;
  area.appendChild(row);
}

/** Append SupplierCard results. */
function appendSupplierCards(area, suppliers) {
  if (!suppliers || suppliers.length === 0) return;
  const row = document.createElement("div");
  row.className = "msg-row";
  const cardsHtml = suppliers.map(s => `
    <div class="supplier-card card">
      <span class="badge b-default">Supplier</span>
      <div class="card-body">
        <div class="card-title">${escHtml(s.name || s.title || "Supplier")}</div>
        <div class="card-meta">${escHtml(s.location || "")} ${s.price ? `· ${escHtml(s.price)}` : ""}</div>
        ${s.description ? `<div class="card-abstract">${escHtml(s.description)}</div>` : ""}
      </div>
    </div>`).join("");
  row.innerHTML = `
    ${aiAvatarHtml()}
    <div class="msg-content">
      <div class="msg-name">Agent Factory <span class="skill-badge">Seller Tools</span></div>
      <div class="ai-bubble"><div class="cards">${cardsHtml}</div></div>
    </div>`;
  area.appendChild(row);
}

/** Append CampaignCard results. */
function appendCampaignCards(area, campaigns) {
  if (!campaigns || campaigns.length === 0) return;
  const row = document.createElement("div");
  row.className = "msg-row";
  const cardsHtml = campaigns.map(c => `
    <div class="campaign-card card">
      <span class="badge b-default">Campaign</span>
      <div class="card-body">
        <div class="card-title">${escHtml(c.name || c.title || "Campaign")}</div>
        <div class="card-meta">${escHtml(c.type || "")} ${c.budget ? `· Budget: ${escHtml(c.budget)}` : ""}</div>
        ${c.description ? `<div class="card-abstract">${escHtml(c.description)}</div>` : ""}
      </div>
    </div>`).join("");
  row.innerHTML = `
    ${aiAvatarHtml()}
    <div class="msg-content">
      <div class="msg-name">Agent Factory <span class="skill-badge">Campaigns</span></div>
      <div class="ai-bubble"><div class="cards">${cardsHtml}</div></div>
    </div>`;
  area.appendChild(row);
}

/* ══════════════════════════════════════════════════════════
   CARD BUILDERS
══════════════════════════════════════════════════════════ */
function buildPaperCard(card) {
  const src    = (card.source || "arxiv").toLowerCase().replace(/[^a-z0-9]/g, "_");
  const bClass = src.includes("arxiv") ? "b-arxiv"
    : src.includes("semantic") || src === "s2" ? "b-s2"
    : src.includes("pubmed") ? "b-pubmed"
    : "b-default";
  const badgeLabel = src.includes("arxiv") ? "arXiv"
    : src.includes("semantic") || src === "s2" ? "S2"
    : src.includes("pubmed") ? "PubMed"
    : (card.source || "").toUpperCase();
  const href   = card.url ? ` href="${escHtml(card.url)}" target="_blank" rel="noopener"` : "";
  const cit    = card.citations
    ? `<span class="cit"><strong>${Number(card.citations).toLocaleString()}</strong> citations</span>` : "";
  const link   = card.url
    ? `<a class="card-link"${href}>${escHtml(new URL(card.url).hostname)} ↗</a>` : "";

  return `<div class="card">
    <span class="badge ${bClass}">${escHtml(badgeLabel)}</span>
    <div class="card-body">
      <a class="card-title"${href}>${escHtml(card.title || "Untitled")}</a>
      <div class="card-meta">${escHtml(card.authors || "")}${card.year ? ` · ${escHtml(card.year)}` : ""}</div>
      ${card.abstract ? `<div class="card-abstract">${escHtml(card.abstract)}</div>` : ""}
      <div class="card-footer">${cit}${link}</div>
    </div>
  </div>`;
}

function buildProductCard(card) {
  const colorMap = { green: "#10b981", amber: "#f59e0b", red: "#f43f5e" };
  const badgeColor = colorMap[card.score_color] || "#8b949e";
  const stars  = card.rating ? "★".repeat(Math.round(parseFloat(card.rating))) + "☆".repeat(Math.max(0, 5 - Math.round(parseFloat(card.rating)))) : "";
  const reviews = card.review_count ? `(${Number(card.review_count).toLocaleString()} reviews)` : (card.reviews || "");
  const bsr    = card.bsr ? `<div class="card-bsr">BSR ${escHtml(card.bsr)}${card.category ? " in " + escHtml(card.category) : ""}</div>` : "";
  const href   = card.url || card.link ? ` href="${escHtml(card.url || card.link)}" target="_blank" rel="noopener"` : "";
  const score  = card.score || card.opportunity_score;

  return `<div class="card" style="position:relative;">
    ${score ? `<div class="card-score-badge" style="background:${badgeColor}">${escHtml(String(score))}</div>` : ""}
    <span class="badge b-amazon">Amazon</span>
    <div class="card-body">
      <a class="card-title"${href}>${escHtml(card.title || "Product")}</a>
      <div class="card-meta">
        <span class="card-price">${escHtml(card.price || "")}</span>
        ${stars ? `<span class="card-stars" title="${escHtml(card.rating || "")}/5">${stars}</span>` : ""}
        <span style="color:var(--text3)">${escHtml(reviews)}</span>
      </div>
      ${bsr}
      ${card.opportunity_reason ? `<div class="card-abstract">${escHtml(card.opportunity_reason)}</div>` : ""}
    </div>
  </div>`;
}

/* ══════════════════════════════════════════════════════════
   TYPING INDICATOR
══════════════════════════════════════════════════════════ */
function showTyping(area) {
  const id = "typing-" + Date.now();
  const row = document.createElement("div");
  row.id = id;
  row.className = "msg-row";
  row.innerHTML = `
    ${aiAvatarHtml()}
    <div class="msg-content">
      <div class="typing-bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div>
    </div>`;
  area.appendChild(row);
  scrollToBottom(area);
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

/* ══════════════════════════════════════════════════════════
   UTILITIES
══════════════════════════════════════════════════════════ */
function setLoading(state, btn, inp) {
  isLoading = state;
  if (btn) btn.disabled = state;
  if (inp) inp.disabled = state;
}

function scrollToBottom(area) {
  if (area) area.scrollTop = area.scrollHeight;
}

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function aiAvatarHtml() {
  return `<div class="avatar ai">
    <svg class="brain-svg" width="22" height="22" viewBox="0 0 100 100" fill="none">
      <defs>
        <linearGradient id="bgl-av" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stop-color="#ff3300"/>
          <stop offset="30%"  stop-color="#ff8800"/>
          <stop offset="52%"  stop-color="#2299ff"/>
          <stop offset="76%"  stop-color="#00cc66"/>
          <stop offset="100%" stop-color="#aa00ee"/>
        </linearGradient>
        <clipPath id="cLav"><path d="M50,10 C43,9 34,14 27,23 C20,32 19,47 20,52 C19,62 23,74 32,80 C38,83 45,85 50,85 Z"/></clipPath>
        <clipPath id="cRav"><path d="M50,10 C57,9 66,14 73,23 C80,32 81,47 80,52 C81,62 77,74 68,80 C62,83 55,85 50,85 Z"/></clipPath>
      </defs>
      <g clip-path="url(#cLav)"><rect x="0" y="0" width="50" height="100" fill="url(#bgl-av)"/></g>
      <path d="M50,10 C43,9 34,14 27,23 C20,32 19,47 20,52 C19,62 23,74 32,80 C38,83 45,85 50,85" stroke="rgba(255,255,255,0.6)" stroke-width="1.5" fill="none"/>
      <g clip-path="url(#cRav)"><rect x="50" y="0" width="50" height="100" fill="url(#bgl-av)"/></g>
      <path d="M50,10 C57,9 66,14 73,23 C80,32 81,47 80,52 C81,62 77,74 68,80 C62,83 55,85 50,85" stroke="rgba(255,255,255,0.6)" stroke-width="1.5" fill="none"/>
      <line x1="50" y1="10" x2="50" y2="85" stroke="rgba(0,0,0,0.55)" stroke-width="1.8"/>
    </svg>
  </div>`;
}

/* Helper called by welcome chip onclick */
function fillInput(text) {
  queryInput.value = text;
  autoResize(queryInput);
  queryInput.focus();
}

function fillShoppingInput(text) {
  switchTab("shopping");
  setTimeout(() => {
    shoppingInput.value = text;
    shoppingInput.focus();
  }, 50);
}
