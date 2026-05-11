/**
 * static/js/app.js
 * Agent Factory — Chat UI JavaScript
 * PROJ-142 (Dilraj Singh)
 */

const API_BASE = "";

const chatArea     = document.getElementById("chat-area");
const input        = document.getElementById("query-input");
const sendBtn      = document.getElementById("send-btn");
const cardsSection = document.getElementById("cards-section");
const cardsGrid    = document.getElementById("cards-grid");
const cardsTitle   = document.getElementById("cards-title");
const statusDot    = document.getElementById("status-dot");

let isLoading = false;

document.addEventListener("DOMContentLoaded", () => {
  checkStatus();
  loadHistory();
  input.addEventListener("keydown", onKeyDown);
  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("input", autoResize);
});

function autoResize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 100) + "px";
}

function onKeyDown(e) {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

async function checkStatus() {
  try {
    const res = await fetch(`${API_BASE}/status`);
    const data = await res.json();
    statusDot.className = data.status === "ok" ? "online" : "offline";
    statusDot.title = data.status === "ok" ? "Agent ready" : "Agent error";
  } catch { statusDot.className = "offline"; statusDot.title = "Agent offline"; }
}

async function sendMessage() {
  const query = input.value.trim();
  if (!query || isLoading) return;
  appendBubble(query, "user");
  input.value = "";
  input.style.height = "auto";
  setLoading(true);
  const typingId = showTyping();
  try {
    const res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    removeTyping(typingId);
    appendBubble(data.response, "agent");
    if (data.cards && data.cards.length > 0) {
      renderCards(data.cards, data.type);
    } else {
      hideCards();
    }
  } catch (err) {
    removeTyping(typingId);
    appendBubble(`Sorry, something went wrong: ${err.message}`, "error");
    hideCards();
  } finally {
    setLoading(false);
    scrollToBottom();
  }
}

async function loadHistory() {
  try {
    const res = await fetch(`${API_BASE}/history`);
    if (!res.ok) return;
    const history = await res.json();
    if (!history || history.length === 0) return;
    const divider = document.createElement("div");
    divider.style.cssText = "text-align:center;color:var(--text-dim);font-size:12px;padding:4px 0;";
    divider.textContent = `── ${history.length} previous queries ──`;
    chatArea.insertBefore(divider, chatArea.firstChild);
    history.slice(-5).forEach(item => {
      appendBubble(item.query, "user", true);
      if (item.summary) appendBubble(item.summary, "agent", true);
    });
  } catch { /* silently ignore */ }
}

function renderCards(cards, type) {
  cardsGrid.innerHTML = "";
  cardsTitle.textContent = type === "amazon"
    ? `🛒 Amazon Results (${cards.length})`
    : `📚 Research Papers (${cards.length})`;
  cards.forEach(card => {
    const el = document.createElement("div");
    el.innerHTML = type === "amazon" ? buildProductCard(card) : buildPaperCard(card);
    cardsGrid.appendChild(el.firstElementChild);
  });
  cardsSection.classList.remove("hidden");
  cardsSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function buildProductCard(card) {
  const colorMap = { green: "#27ae60", amber: "#f39c12", red: "#e74c3c" };
  const badgeColor = colorMap[card.score_color] || "#888";
  const stars = "★".repeat(Math.round(card.rating)) + "☆".repeat(5 - Math.round(card.rating));
  const reviews = card.review_count ? `(${card.review_count.toLocaleString()} reviews)` : "";
  const bsr = card.bsr ? `<div class="card-bsr">BSR #${card.bsr}${card.category ? " in " + card.category : ""}</div>` : "";
  const href = card.url ? `href="${escHtml(card.url)}" target="_blank"` : "";
  return `<div class="card product-card" data-score="${card.score}">
    <div class="card-score-badge" style="background:${badgeColor}">${card.score}</div>
    <div class="card-body">
      <a ${href} class="card-title">${escHtml(card.title)}</a>
      <div class="card-meta">
        <span class="card-price">${escHtml(card.price || "N/A")}</span>
        <span class="card-stars" title="${card.rating}/5">${stars}</span>
        <span>${reviews}</span>
      </div>
      ${bsr}
    </div>
  </div>`;
}

function buildPaperCard(card) {
  const source = (card.source || "arxiv").replace("_", " ").toUpperCase();
  const href = card.url ? `href="${escHtml(card.url)}" target="_blank"` : "";
  const citations = card.citations
    ? `<span class="card-citations" data-citations="${card.citations}">📚 ${card.citations.toLocaleString()} citations</span>`
    : "";
  return `<div class="card paper-card" data-citations="${card.citations || 0}">
    <div class="card-source-tag">${escHtml(source)}</div>
    <div class="card-body">
      <a ${href} class="card-title">${escHtml(card.title)}</a>
      <div class="card-meta">
        <span class="card-authors">${escHtml(card.authors || "")}</span>
        ${card.year ? `<span class="card-year">(${escHtml(card.year)})</span>` : ""}
        ${citations}
      </div>
      <p class="card-abstract">${escHtml(card.abstract || "")}</p>
    </div>
  </div>`;
}

function hideCards() {
  cardsSection.classList.add("hidden");
  cardsGrid.innerHTML = "";
}

function appendBubble(text, type, prepend = false) {
  const el = document.createElement("div");
  const cls = type === "user" ? "user-bubble" : type === "error" ? "error-bubble" : "agent-bubble";
  el.className = `chat-bubble ${cls}`;
  el.textContent = text;
  if (prepend) {
    const divider = chatArea.querySelector("div[style]");
    chatArea.insertBefore(el, divider ? divider.nextSibling : chatArea.firstChild);
  } else {
    chatArea.appendChild(el);
  }
  return el;
}

function showTyping() {
  const id = "typing-" + Date.now();
  const el = document.createElement("div");
  el.id = id;
  el.className = "chat-bubble typing-bubble";
  el.innerHTML = `<div class="typing-dots"><span></span><span></span><span></span></div>`;
  chatArea.appendChild(el);
  scrollToBottom();
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function setLoading(state) {
  isLoading = state;
  sendBtn.disabled = state;
  input.disabled = state;
}

function scrollToBottom() { chatArea.scrollTop = chatArea.scrollHeight; }

function escHtml(str) {
  return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
