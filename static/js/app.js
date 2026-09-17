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

// Seller Tools tab
const shoppingArea  = document.getElementById("shopping-area");
const shoppingInput = document.getElementById("shopping-input");
const shoppingBtn   = document.getElementById("shopping-btn");

// Integrity tab
const integrityInput = document.getElementById("integrity-input");
const integrityBtn   = document.getElementById("integrity-btn");

// Literature search (inside Literature AI tab)
const literatureArea  = document.getElementById("literature-area");
const literatureInput = document.getElementById("literature-input");
const literatureBtn   = document.getElementById("literature-btn");

let isLoading = false;
let activeTab = "shopping";
let activeLitMode = "search"; // "search" | "general" | "integrity"

/* ── Attachment state ─────────────────────────────────────── */
// Each entry: { name, ext, size, text, dataUrl }
const attachState = { shopping: [], literature: [], integrity: [], general: [] };

/* ══════════════════════════════════════════════════════════
   ATTACHMENT SYSTEM
══════════════════════════════════════════════════════════ */

/** Map extension → emoji icon */
function fileIcon(ext) {
  const map = {
    pdf: "📄", docx: "📝", doc: "📝", txt: "📃", md: "📃",
    csv: "📊", json: "📋", png: "🖼", jpg: "🖼", jpeg: "🖼",
    gif: "🖼", webp: "🖼", bmp: "🖼",
  };
  return map[(ext || "").toLowerCase()] || "📁";
}

/** Human-readable file size */
function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

/** Lazily inject a CDN script, returns Promise that resolves when loaded */
function loadScript(src, globalCheck) {
  return new Promise((resolve, reject) => {
    if (globalCheck && window[globalCheck]) return resolve();
    const s = document.createElement("script");
    s.src = src; s.onload = resolve; s.onerror = reject;
    document.head.appendChild(s);
  });
}

/** Extract text from a PDF file using PDF.js (lazy-loaded) */
async function extractPdfText(file) {
  await loadScript(
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js",
    "pdfjsLib"
  );
  window.pdfjsLib.GlobalWorkerOptions.workerSrc =
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  const buf = await file.arrayBuffer();
  const pdf = await window.pdfjsLib.getDocument({ data: buf }).promise;
  let text = "";
  for (let i = 1; i <= Math.min(pdf.numPages, 30); i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();
    text += content.items.map(it => it.str).join(" ") + "\n";
  }
  return text.trim();
}

/** Extract text from a DOCX file using mammoth.js (lazy-loaded) */
async function extractDocxText(file) {
  await loadScript(
    "https://cdn.jsdelivr.net/npm/mammoth@1.8.0/mammoth.browser.min.js",
    "mammoth"
  );
  const buf = await file.arrayBuffer();
  const result = await window.mammoth.extractRawText({ arrayBuffer: buf });
  return result.value.trim();
}

/** Read file — returns { text, dataUrl } based on type */
async function readFile(file) {
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const imgExts = ["png", "jpg", "jpeg", "gif", "webp", "bmp"];

  if (ext === "pdf") {
    try { return { text: await extractPdfText(file), dataUrl: null }; }
    catch { return { text: `[PDF: ${file.name} — could not extract text]`, dataUrl: null }; }
  }
  if (ext === "docx" || ext === "doc") {
    try { return { text: await extractDocxText(file), dataUrl: null }; }
    catch { return { text: `[Document: ${file.name} — could not extract text]`, dataUrl: null }; }
  }
  if (imgExts.includes(ext)) {
    return new Promise(resolve => {
      const fr = new FileReader();
      fr.onload = () => resolve({ text: null, dataUrl: fr.result });
      fr.readAsDataURL(file);
    });
  }
  // Plain text types
  return new Promise(resolve => {
    const fr = new FileReader();
    fr.onload = () => resolve({ text: fr.result, dataUrl: null });
    fr.onerror  = () => resolve({ text: `[${file.name} — could not read]`, dataUrl: null });
    fr.readAsText(file);
  });
}

/** Trigger file picker for a given panel */
function triggerAttach(panel) {
  let inp = document.getElementById("attach-file-" + panel);
  if (!inp) {
    inp = document.createElement("input");
    inp.type = "file"; inp.id = "attach-file-" + panel; inp.style.display = "none";
    inp.multiple = true;
    inp.accept = ".txt,.md,.csv,.json,.pdf,.docx,.doc,.png,.jpg,.jpeg,.gif,.webp,.bmp";
    inp.addEventListener("change", () => handleFileSelect(inp.files, panel));
    document.body.appendChild(inp);
  }
  inp.value = ""; // reset so same file can be re-attached
  inp.click();
}

/** Process selected files, read contents, render chips */
async function handleFileSelect(files, panel) {
  if (!files || files.length === 0) return;
  for (const file of Array.from(files)) {
    if (file.size > 20 * 1024 * 1024) {
      alert(`"${file.name}" is too large (max 20 MB).`); continue;
    }
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const { text, dataUrl } = await readFile(file);
    const attachment = { name: file.name, ext, size: file.size, text, dataUrl };
    attachState[panel].push(attachment);
    addAttachChip(panel, attachment, attachState[panel].length - 1);
  }
}

/** Render a chip in the attach strip for a given panel */
function addAttachChip(panel, att, idx) {
  const strip = document.getElementById(panel + "-attach-strip");
  if (!strip) return;
  const chip = document.createElement("div");
  chip.className = "attach-chip";
  chip.id = `attach-chip-${panel}-${idx}`;

  let iconHtml;
  if (att.dataUrl) {
    iconHtml = `<img class="attach-chip-thumb" src="${att.dataUrl}" alt="">`;
  } else {
    iconHtml = `<span class="attach-chip-icon">${fileIcon(att.ext)}</span>`;
  }

  chip.innerHTML =
    iconHtml +
    `<span class="attach-chip-name" title="${escHtml(att.name)}">${escHtml(att.name)}</span>` +
    `<span class="attach-chip-size">${formatSize(att.size)}</span>` +
    `<button class="attach-chip-remove" onclick="removeAttachment('${panel}',${idx})" title="Remove">✕</button>`;
  strip.appendChild(chip);
}

/** Remove one attachment by index */
function removeAttachment(panel, idx) {
  attachState[panel].splice(idx, 1);
  // Re-render the whole strip
  renderAttachStrip(panel);
}

/** Re-render all chips for a panel (called after removal) */
function renderAttachStrip(panel) {
  const strip = document.getElementById(panel + "-attach-strip");
  if (!strip) return;
  strip.innerHTML = "";
  attachState[panel].forEach((att, i) => addAttachChip(panel, att, i));
}

/** Clear all attachments for a panel */
function clearAttachments(panel) {
  attachState[panel] = [];
  const strip = document.getElementById(panel + "-attach-strip");
  if (strip) strip.innerHTML = "";
}

/**
 * Build extra context string from attachments.
 * Returns { contextText, attachments }
 */
function getAttachContext(panel) {
  const atts = attachState[panel];
  let contextText = "";
  for (const att of atts) {
    if (att.text) {
      contextText += `\n\n--- Attached file: ${att.name} ---\n${att.text}`;
    } else if (att.dataUrl) {
      contextText += `\n[Image attached: ${att.name}]`;
    }
  }
  return { contextText, attachments: [...atts] };
}

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

  // Amazon Seller AI input — Enter to submit
  shoppingInput.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); sendShoppingQuery(); }
  });
  shoppingBtn.addEventListener("click", sendShoppingQuery);

  // Literature search input — Enter to search
  literatureInput.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); sendLiteratureQuery(); }
  });
  literatureBtn.addEventListener("click", sendLiteratureQuery);

  // General search input — Enter to ask
  const generalInput = document.getElementById("general-input");
  const generalBtn   = document.getElementById("general-btn");
  if (generalInput) generalInput.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); sendGeneralQuery(); }
  });
  if (generalBtn) generalBtn.addEventListener("click", sendGeneralQuery);

  // Integrity check input — Enter to submit, Ctrl+Enter for new line
  integrityInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.ctrlKey) { e.preventDefault(); sendIntegrityCheck(); }
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
   LITERATURE AI — MODE SWITCHING
══════════════════════════════════════════════════════════ */
/* ── Quick-action chip helpers ──────────────────────────────── */
function prefillShopping(prefix, hint) {
  shoppingInput.value = prefix;
  shoppingInput.placeholder = hint || shoppingInput.placeholder;
  shoppingInput.focus();
  // Move cursor to end
  shoppingInput.setSelectionRange(prefix.length, prefix.length);
}

function prefillLiterature() {
  setLitMode("search");
  literatureInput.placeholder = "e.g. transformers in NLP, quantum computing…";
  literatureInput.focus();
}

function switchToIntegrity(mode) {
  setLitMode("integrity");
  setIntegrityMode(mode);
  const integrityInput = document.getElementById("integrity-input");
  if (integrityInput) integrityInput.focus();
}

function setLitMode(mode) {
  activeLitMode = mode;
  document.getElementById("lit-search-panel").style.display    = mode === "search"    ? "flex" : "none";
  document.getElementById("lit-general-panel").style.display   = mode === "general"   ? "flex" : "none";
  document.getElementById("lit-integrity-panel").style.display = mode === "integrity" ? "flex" : "none";
  document.getElementById("lit-mode-search").classList.toggle("active",    mode === "search");
  document.getElementById("lit-mode-general").classList.toggle("active",   mode === "general");
  document.getElementById("lit-mode-integrity").classList.toggle("active", mode === "integrity");
}

function setLitQuery(query) {
  setLitMode("search");
  literatureInput.value = query;
  sendLiteratureQuery();
}

/* ══════════════════════════════════════════════════════════
   LITERATURE SEARCH — POST /query (literature type)
══════════════════════════════════════════════════════════ */
async function sendLiteratureQuery() {
  const query = literatureInput.value.trim();
  const { contextText, attachments } = getAttachContext("literature");
  if (!query && !contextText || isLoading) return;
  const displayQuery = query || "(attached file)";
  const fullQuery    = query + contextText;

  appendUserMsg(literatureArea, displayQuery, attachments);
  literatureInput.value = "";
  clearAttachments("literature");
  setLoading(true, literatureBtn, literatureInput);
  const typingId = showTyping(literatureArea);

  try {
    const res = await fetch(`${API_BASE}/literature`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: fullQuery }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    removeTyping(typingId);

    // /literature returns { papers, synthesis, total, query, error }
    const cards = data.papers || [];
    if (data.error && cards.length === 0) {
      // Both sources failed — show a helpful error
      appendErrorMsg(literatureArea,
        "Could not reach academic databases right now. " +
        (data.error.includes("rate") ? "Semantic Scholar is rate-limited — wait 1 min and try again." :
         data.error.includes("arXiv") ? "arXiv timed out — try again in a moment." :
         data.error));
    } else {
      let summary = data.synthesis
        || `Found **${data.total || cards.length}** papers for **"${data.query || query}"**`;
      // If one source failed but we still got results, append a subtle inline note
      if (data.error && cards.length > 0) {
        const note = data.error.includes("rate")
          ? "_⚠️ Semantic Scholar was rate-limited — showing arXiv results only. Try again in ~1 min for more._"
          : `_⚠️ Note: ${data.error}_`;
        summary = summary + "\n\n" + note;
      }
      appendAgentBubble(literatureArea, summary, cards, "literature");
    }
  } catch (err) {
    removeTyping(typingId);
    appendErrorMsg(literatureArea, err.message);
  } finally {
    setLoading(false, literatureBtn, literatureInput);
    scrollToBottom(literatureArea);
  }
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
        switchTab("shopping");
        shoppingInput.value = item.query || "";
        shoppingInput.focus();
      };
      historyList.appendChild(el);
    });
  } catch { /* silently ignore */ }
}


/* ══════════════════════════════════════════════════════════
   SHOPPING TAB — POST /query (amazon type)
══════════════════════════════════════════════════════════ */
async function sendShoppingQuery() {
  const query = shoppingInput.value.trim();
  const { contextText, attachments } = getAttachContext("shopping");
  if (!query && !contextText || isLoading) return;
  const displayQuery = query || "(attached file)";
  const fullQuery    = query + contextText;

  appendUserMsg(shoppingArea, displayQuery, attachments);
  shoppingInput.value = "";
  clearAttachments("shopping");
  setLoading(true, shoppingBtn, shoppingInput);
  const typingId = showTyping(shoppingArea);

  try {
    const res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: fullQuery }),
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
   GENERAL SEARCH TAB — POST /ask
══════════════════════════════════════════════════════════ */
async function sendGeneralQuery() {
  const generalInput = document.getElementById("general-input");
  const generalBtn   = document.getElementById("general-btn");
  const generalArea  = document.getElementById("general-area");
  const question = generalInput.value.trim();
  const { contextText, attachments } = getAttachContext("general");
  if (!question && !contextText || isLoading) return;

  const displayQ  = question || "(attached file)";
  const fullQ     = question + contextText;

  appendUserMsg(generalArea, displayQ, attachments);
  generalInput.value = "";
  clearAttachments("general");
  setLoading(true, generalBtn, generalInput);
  const typingId = showTyping(generalArea);

  try {
    const res = await fetch(`${API_BASE}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: fullQ }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    removeTyping(typingId);
    if (data.error && !data.answer) {
      appendErrorMsg(generalArea, data.error);
    } else {
      appendAgentBubble(generalArea, data.answer, [], "general");
    }
  } catch (err) {
    removeTyping(typingId);
    appendErrorMsg(generalArea, err.message);
  } finally {
    setLoading(false, generalBtn, generalInput);
    scrollToBottom(generalArea);
  }
}

function prefillGeneral(prefix) {
  setLitMode("general");
  const inp = document.getElementById("general-input");
  if (!inp) return;
  inp.value = prefix;
  inp.focus();
  inp.setSelectionRange(prefix.length, prefix.length);
}

/* ══════════════════════════════════════════════════════════
   INTEGRITY TAB — POST /integrity
══════════════════════════════════════════════════════════ */
async function sendIntegrityCheck() {
  const typed = integrityInput.value.trim();
  const { contextText, attachments } = getAttachContext("integrity");
  // For integrity, file text replaces or supplements typed text
  const text = typed + contextText;
  if (!text || isLoading) return;
  const integrityArea = document.getElementById("integrity-area");

  const displayText = typed || (attachments[0] ? attachments[0].name : "(attached file)");
  appendUserMsg(integrityArea, displayText.length > 100 ? displayText.slice(0, 100) + "…" : displayText, attachments);
  integrityInput.value = "";
  clearAttachments("integrity");
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
    cardsHtml = `<div class="cards">${cards.map(c => {
      if (type === "amazon" || type === "shopping") return buildProductCard(c);
      if (type === "supplier_finder") return buildSupplierCard(c);
      if (type === "ppc_builder") return buildCampaignCard(c);
      return buildPaperCard(c);
    }).join("")}</div>`;
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
    : type === "supplier_finder" ? "Suppliers"
    : type === "ppc_builder" ? "PPC Campaign"
    : type === "literature" ? "Literature"
    : type === "integrity" ? "Integrity"
    : type === "general" ? "Ask Anything"
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

/** Append a plain user message row, with optional attachment previews. */
function appendUserMsg(area, text, attachments = []) {
  const row = document.createElement("div");
  row.className = "msg-row user";

  let attachHtml = "";
  if (attachments.length > 0) {
    attachHtml = `<div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:6px;justify-content:flex-end">` +
      attachments.map(a => {
        if (a.dataUrl) {
          return `<img src="${a.dataUrl}" style="max-width:110px;max-height:72px;border-radius:6px;object-fit:cover;border:1px solid rgba(124,58,237,0.3)" title="${escHtml(a.name)}">`;
        }
        return `<span style="background:rgba(124,58,237,0.12);border:1px solid rgba(124,58,237,0.28);border-radius:6px;padding:3px 8px;font-size:11px;color:#c4b5fd;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${fileIcon(a.ext)} ${escHtml(a.name)}</span>`;
      }).join("") +
      "</div>";
  }

  row.innerHTML = `
    <div class="msg-content" style="display:flex;flex-direction:column;align-items:flex-end;">
      <div class="msg-name" style="justify-content:flex-end;">You</div>
      ${attachHtml}
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
  const cardsHtml = suppliers.map(s => buildSupplierCard(s)).join("");
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
function buildSupplierCard(card) {
  const verified = card.verified
    ? `<span class="badge b-arxiv">✔ Verified</span>` : "";
  const ta = card.trade_assurance
    ? `<span class="badge b-pubmed">Trade Assurance</span>` : "";
  const demo = card.demo_data
    ? `<span class="badge" style="background:#6b7280">Demo</span>` : "";
  const href = card.url ? ` href="${escHtml(card.url)}" target="_blank" rel="noopener"` : "";
  const price = card.price_range && card.price_range !== "Price on request"
    ? card.price_range : "Price on request";
  return `
    <div class="card">
      <div class="card-body">
        <a class="card-title"${href}>${escHtml(card.supplier_name || "Supplier")}</a>
        <div class="card-meta" style="margin-top:2px">${escHtml(card.product_title || "")} ${verified}${ta}${demo}</div>
        <div style="margin-top:8px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
          <span style="font-size:1.05rem;font-weight:700;color:var(--emerald)">💰 ${escHtml(price)}</span>
          <span style="color:#aaa;font-size:0.85rem">MOQ: ${escHtml(String(card.moq || "N/A"))}</span>
          <span style="color:#aaa;font-size:0.85rem">⭐ ${escHtml(String(card.rating || "N/A"))}</span>
        </div>
      </div>
    </div>`;
}

function buildCampaignCard(card) {
  const matchColours = { Broad: "#6366f1", Phrase: "#f59e0b", Exact: "#10b981" };
  const matchIcons   = { Broad: "🔍", Phrase: "💬", Exact: "🎯" };
  const colour = matchColours[card.match_type] || "#6b7280";
  const icon   = matchIcons[card.match_type]   || "📌";
  const clicks = card.estimated_clicks || 0;
  const bid    = card.suggested_bid || "N/A";
  return `
    <div class="card" style="border-left:3px solid ${colour};padding:0">
      <div class="card-body" style="padding:12px 14px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <span style="font-size:1rem">${icon}</span>
          <span style="font-size:0.95rem;font-weight:600;color:#e2e8f0;flex:1">${escHtml(card.keyword || "Keyword")}</span>
        </div>
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span style="background:${colour};color:#fff;font-size:0.72rem;font-weight:700;padding:2px 8px;border-radius:4px;letter-spacing:0.05em">${escHtml(card.match_type || "")}</span>
          <span style="color:#34d399;font-size:0.88rem;font-weight:700">💰 ${escHtml(String(bid))}</span>
          <span style="color:#94a3b8;font-size:0.82rem">~${escHtml(String(clicks))} clicks/day</span>
        </div>
      </div>
    </div>`;
}

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
  switchTab("shopping");
  setTimeout(() => {
    shoppingInput.value = text;
    shoppingInput.focus();
  }, 50);
}

function fillShoppingInput(text) {
  switchTab("shopping");
  setTimeout(() => {
    shoppingInput.value = text;
    shoppingInput.focus();
  }, 50);
}

/* ══ RECEPTIONIST DASHBOARD (PROJ-386) ══ */

function switchReceptTab(tabName) {
  document.querySelectorAll(".recept-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".recept-panel[id^='rtab-']").forEach(p => (p.style.display = "none"));
  const btn = document.querySelector(`.recept-tab[data-rtab="${tabName}"]`);
  if (btn) btn.classList.add("active");
  const panel = document.getElementById(`rtab-${tabName}`);
  if (panel) panel.style.display = "flex";
  if (tabName === "activity")    loadReceptActivity();
  if (tabName === "analytics")   loadAnalyticsDashboard();
  if (tabName === "delivery")    loadDeliveryHistory();
  if (tabName === "escalations") loadReceptEscalations();
  if (tabName === "calendar")    loadReceptCalendar();
}

function prefillReceptionist(text) {
  const inp = document.getElementById("receptionist-input");
  if (inp) { inp.value = text; inp.focus(); }
  switchTab("receptionist");
}

async function sendReceptionistQuery() {
  const inp = document.getElementById("receptionist-input");
  const msgs = document.getElementById("receptionist-area");
  const query = inp ? inp.value.trim() : "";
  if (!query || !msgs) return;
  inp.value = "";
  appendReceptMsg("user", query);
  appendReceptMsg("assistant", "…", "recept-thinking");
  try {
    const res = await fetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    const thinking = msgs.querySelector(".recept-thinking");
    if (thinking) thinking.remove();
    appendReceptMsg("assistant", data.response || data.error || "No response");
  } catch (e) {
    const thinking = msgs.querySelector(".recept-thinking");
    if (thinking) thinking.remove();
    appendReceptMsg("assistant", "Error: " + e.message);
  }
}

function appendReceptMsg(role, text, extraClass) {
  const msgs = document.getElementById("receptionist-area");
  if (!msgs) return;
  const div = document.createElement("div");
  div.className = `chat-msg ${role}${extraClass ? " " + extraClass : ""}`;
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

async function loadReceptStats() {
  try {
    const res = await fetch("/activity/stats");
    if (!res.ok) return;
    const d = await res.json();
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? "—"; };
    set("stat-calls", d.calls ?? d.voice ?? 0);
    set("stat-sms", d.sms ?? 0);
    set("stat-booked", d.appointments ?? d.booked ?? 0);
    set("stat-escalations", d.escalations ?? 0);
  } catch (_) { /* backend not yet wired — silently skip */ }
}

async function loadReceptActivity() {
  const feed = document.getElementById("activity-feed");
  if (!feed) return;
  try {
    const res = await fetch("/activity");
    if (!res.ok) throw new Error("no data");
    const items = await res.json();
    if (!items.length) { feed.innerHTML = '<p class="recept-empty">No recent activity.</p>'; return; }
    feed.innerHTML = items.map(i => `
      <div class="recept-row">
        <div class="recept-row-header">
          <span class="recept-row-badge badge-${(i.channel||"web").toLowerCase()}">${i.channel || "web"}</span>
          <span class="recept-row-time">${i.time || ""}</span>
        </div>
        <div class="recept-row-body">${escapeHtml(i.summary || i.message || "")}</div>
      </div>`).join("");
  } catch (_) { feed.innerHTML = '<p class="recept-empty">Activity data loading…</p>'; }
}

async function loadReceptEscalations() {
  const feed = document.getElementById("escalations-feed");
  if (!feed) return;
  try {
    const res = await fetch("/escalations");
    if (!res.ok) throw new Error("no data");
    const items = await res.json();
    if (!items.length) { feed.innerHTML = '<p class="recept-empty">No open escalations.</p>'; return; }
    feed.innerHTML = items.map(i => `
      <div class="recept-row">
        <div class="recept-row-header">
          <span class="recept-row-badge badge-${(i.priority||"web").toLowerCase()}">${i.priority || "normal"}</span>
          <span class="recept-row-time">${i.time || ""}</span>
        </div>
        <div class="recept-row-body">${escapeHtml(i.reason || i.message || "")}</div>
      </div>`).join("");
  } catch (_) { feed.innerHTML = '<p class="recept-empty">Escalation data loading…</p>'; }
}

async function loadReceptCalendar() {
  const feed = document.getElementById("calendar-feed");
  if (!feed) return;
  try {
    const res = await fetch("/calendar/appointments");
    if (!res.ok) throw new Error("no data");
    const items = await res.json();
    if (!items.length) { feed.innerHTML = '<p class="recept-empty">No upcoming appointments.</p>'; return; }
    feed.innerHTML = items.map(i => `
      <div class="cal-row">
        <div class="cal-row-time">${escapeHtml(i.datetime || i.time || "")}</div>
        <div class="cal-row-summary">${escapeHtml(i.summary || i.title || "")}</div>
        <div class="cal-row-from">${escapeHtml(i.caller || i.from || "")}</div>
      </div>`).join("");
  } catch (_) { feed.innerHTML = '<p class="recept-empty">Calendar data loading…</p>'; }
}

function escapeHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

/* Wire up receptionist input on Enter & initialize Personalisation */
document.addEventListener("DOMContentLoaded", () => {
  const inp = document.getElementById("receptionist-input");
  if (inp) {
    inp.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendReceptionistQuery(); } });
  }
  /* Poll stats every 30s when receptionist tab is visible */
  loadReceptStats();
  setInterval(loadReceptStats, 30_000);

  /* Initialize User Personalisation (PROJ-401, PROJ-444) */
  initPersonalisation();
});

/* ══ ANALYTICS & REPORTING (PROJ-398, PROJ-435, PROJ-436) ══ */

async function loadAnalyticsDashboard() {
  try {
    const res = await fetch("/analytics/summary");
    if (!res.ok) return;
    const data = await res.json();
    const sum = data.summary || {};

    const elDeliveryRate = document.getElementById("kpi-delivery-rate");
    const elResponseRate = document.getElementById("kpi-response-rate");
    const elTotalSent = document.getElementById("kpi-total-sent");
    const elTotalFailed = document.getElementById("kpi-total-failed");
    const elInflight = document.getElementById("kpi-inflight");
    const elSuppressed = document.getElementById("kpi-suppressed-count");

    if (elDeliveryRate) elDeliveryRate.textContent = `${sum.delivery_rate_pct ?? 100}%`;
    if (elResponseRate) elResponseRate.textContent = `${sum.response_rate_pct ?? 0}%`;
    if (elTotalSent) elTotalSent.textContent = sum.total_sent ?? 0;
    if (elTotalFailed) elTotalFailed.textContent = (sum.failed ?? 0) + (sum.bounced ?? 0);
    if (elInflight) elInflight.textContent = `In-flight: ${sum.in_flight ?? 0}`;
    if (elSuppressed) elSuppressed.textContent = `Suppressed emails: ${sum.suppressed_emails_count ?? 0}`;

    // Render Charts
    renderTrendChart(data.daily_trends || []);
    renderChannelChart(data.channels || {});
  } catch (err) {
    console.error("Failed to load analytics:", err);
  }
}

function renderTrendChart(trends) {
  const svg = document.getElementById("trend-chart-svg");
  if (!svg) return;
  if (!trends || trends.length === 0) {
    svg.innerHTML = `<text x="300" y="100" fill="var(--text2)" font-size="13" text-anchor="middle">No delivery data yet. Click "Seed Demo Data" above to view trends.</text>`;
    return;
  }

  const maxVal = Math.max(...trends.map(t => Math.max(t.sent || 0, t.delivered || 0)), 5);
  const width = 600;
  const height = 200;
  const padLeft = 40;
  const padBottom = 30;
  const chartW = width - padLeft - 20;
  const chartH = height - padBottom - 20;

  const stepX = chartW / Math.max(trends.length - 1, 1);

  let sentPoints = "";
  let delPoints = "";
  let labelsHtml = "";
  let barsHtml = "";

  trends.forEach((t, i) => {
    const x = padLeft + i * stepX;
    const ySent = height - padBottom - ((t.sent || 0) / maxVal) * chartH;
    const yDel = height - padBottom - ((t.delivered || 0) / maxVal) * chartH;
    sentPoints += `${x},${ySent} `;
    delPoints += `${x},${yDel} `;

    const dateStr = (t.date || "").slice(5);
    labelsHtml += `<text x="${x}" y="${height - 10}" fill="var(--text2)" font-size="10" text-anchor="middle">${escapeHtml(dateStr)}</text>`;

    // Mini bar for failures
    if (t.failed) {
      const barH = (t.failed / maxVal) * chartH;
      barsHtml += `<rect x="${x - 6}" y="${height - padBottom - barH}" width="12" height="${barH}" fill="#f43f5e" opacity="0.6" rx="2" />`;
    }
  });

  svg.innerHTML = `
    <!-- Grid line -->
    <line x1="${padLeft}" y1="${height - padBottom}" x2="${width - 20}" y2="${height - padBottom}" stroke="var(--border)" stroke-width="1" />
    <line x1="${padLeft}" y1="20" x2="${width - 20}" y2="20" stroke="var(--border)" stroke-dasharray="3,3" />

    <!-- Failure Bars -->
    ${barsHtml}

    <!-- Trend lines -->
    <polyline fill="none" stroke="#6366f1" stroke-width="3" stroke-linecap="round" points="${sentPoints.trim()}" />
    <polyline fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" points="${delPoints.trim()}" />

    <!-- Labels -->
    ${labelsHtml}

    <!-- Legend -->
    <circle cx="450" cy="15" r="4" fill="#6366f1" />
    <text x="460" y="18" fill="var(--text2)" font-size="11">Sent</text>
    <circle cx="510" cy="15" r="4" fill="#10b981" />
    <text x="520" y="18" fill="var(--text2)" font-size="11">Delivered</text>
    <rect x="565" y="11" width="8" height="8" fill="#f43f5e" rx="1" />
    <text x="578" y="18" fill="var(--text2)" font-size="11">Failed</text>
  `;
}

function renderChannelChart(channels) {
  const svg = document.getElementById("channel-chart-svg");
  if (!svg) return;

  const sms = channels.sms?.total || 0;
  const email = channels.email?.total || 0;
  const voice = channels.voice?.total || 0;
  const total = sms + email + voice;

  if (total === 0) {
    svg.innerHTML = `<text x="125" y="100" fill="var(--text2)" font-size="12" text-anchor="middle">No channel volume</text>`;
    return;
  }

  const cx = 85;
  const cy = 100;
  const r = 60;
  const innerR = 40;

  // Simple clean SVG donut breakdown representation
  const pSms = (sms / total) * 100;
  const pEmail = (email / total) * 100;
  const pVoice = (voice / total) * 100;

  svg.innerHTML = `
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--surface3)" stroke-width="20" />
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#22c55e" stroke-width="20"
      stroke-dasharray="${(pSms / 100) * 377} 377" transform="rotate(-90 ${cx} ${cy})" />
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#3b82f6" stroke-width="20"
      stroke-dasharray="${(pEmail / 100) * 377} 377" stroke-dashoffset="${-((pSms / 100) * 377)}" transform="rotate(-90 ${cx} ${cy})" />
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#a78bfa" stroke-width="20"
      stroke-dasharray="${(pVoice / 100) * 377} 377" stroke-dashoffset="${-(((pSms + pEmail) / 100) * 377)}" transform="rotate(-90 ${cx} ${cy})" />

    <text x="${cx}" y="${cy + 5}" fill="var(--text)" font-size="14" font-weight="700" text-anchor="middle">${total}</text>
    <text x="${cx}" y="${cy + 20}" fill="var(--text2)" font-size="10" text-anchor="middle">Total</text>

    <!-- Legend -->
    <circle cx="165" cy="70" r="5" fill="#22c55e" />
    <text x="178" y="74" fill="var(--text)" font-size="11">SMS (${Math.round(pSms)}%)</text>
    <circle cx="165" cy="100" r="5" fill="#3b82f6" />
    <text x="178" y="104" fill="var(--text)" font-size="11">Email (${Math.round(pEmail)}%)</text>
    <circle cx="165" cy="130" r="5" fill="#a78bfa" />
    <text x="178" y="134" fill="var(--text)" font-size="11">Voice (${Math.round(pVoice)}%)</text>
  `;
}

async function seedSampleAnalyticsData() {
  try {
    const res = await fetch("/analytics/seed-demo-data?count=25", { method: "POST" });
    if (res.ok) {
      loadAnalyticsDashboard();
      if (document.querySelector('.recept-tab[data-rtab="delivery"]')?.classList.contains("active")) {
        loadDeliveryHistory();
      }
    }
  } catch (e) {
    console.error("Failed to seed demo data:", e);
  }
}

/* ══ DELIVERY HISTORY & RETRY (PROJ-397, PROJ-434) ══ */

let deliverySearchTimeout = null;
function debounceDeliverySearch() {
  clearTimeout(deliverySearchTimeout);
  deliverySearchTimeout = setTimeout(loadDeliveryHistory, 300);
}

async function loadDeliveryHistory() {
  const tbody = document.getElementById("delivery-table-body");
  if (!tbody) return;

  const searchVal = document.getElementById("delivery-search-input")?.value.trim() || "";
  const channelVal = document.getElementById("delivery-channel-filter")?.value || "all";
  const statusVal = document.getElementById("delivery-status-filter")?.value || "all";

  const params = new URLSearchParams();
  params.set("limit", "50");
  if (searchVal) params.set("search", searchVal);
  if (channelVal !== "all") params.set("channel", channelVal);
  if (statusVal !== "all") params.set("status", statusVal);

  try {
    const res = await fetch(`/delivery/history?${params.toString()}`);
    if (!res.ok) throw new Error("Failed to fetch delivery logs");
    const data = await res.json();
    const items = data.items || [];

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text2);padding:24px;">No delivery records match filter criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map(item => {
      const badgeClass = `badge-${item.status || "queued"}`;
      const channelIcon = item.channel === "email" ? "✉️" : (item.channel === "voice" ? "📞" : "💬");
      const errorText = item.error_message || item.error_code || "—";
      const canRetry = ["failed", "undelivered", "bounced"].includes((item.status || "").toLowerCase());

      return `
        <tr>
          <td style="color:var(--text2);font-size:11px;">${escapeHtml(item.time_ago || item.sent_at?.slice(11, 16) || "—")}</td>
          <td>${channelIcon} ${escapeHtml(item.channel?.toUpperCase() || "SMS")}</td>
          <td style="font-weight:500;">${escapeHtml(item.recipient || "—")}</td>
          <td><span style="font-size:11px;color:var(--text2);">${escapeHtml(item.reminder_type || "general")}</span></td>
          <td><span class="delivery-badge ${badgeClass}">${escapeHtml(item.status || "queued")}</span></td>
          <td style="color:${canRetry ? '#f43f5e' : 'var(--text2)'};max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(errorText)}">${escapeHtml(errorText)}</td>
          <td>
            ${canRetry ? `<button class="retry-action-btn" onclick="retryDeliveryRecord('${escapeHtml(item.message_id)}')">↻ Retry</button>` : `<span style="color:var(--text3);font-size:11px;">✓ Done</span>`}
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#f43f5e;padding:20px;">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

async function retryDeliveryRecord(messageId) {
  try {
    const res = await fetch(`/delivery/retry/${encodeURIComponent(messageId)}`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Failed to retry delivery.");
      return;
    }
    loadDeliveryHistory();
    loadAnalyticsDashboard();
  } catch (err) {
    alert("Retry failed: " + err.message);
  }
}

/* ── Send Reminder Modal ── */
function openSendReminderModal() {
  const modal = document.getElementById("send-reminder-modal");
  if (modal) modal.style.display = "flex";
}

function closeSendReminderModal() {
  const modal = document.getElementById("send-reminder-modal");
  if (modal) modal.style.display = "none";
}

async function submitSendReminder() {
  const recipient = document.getElementById("rem-recipient")?.value.trim();
  const channel = document.getElementById("rem-channel")?.value || "sms";
  const reminder_type = document.getElementById("rem-type")?.value || "appointment";
  const message = document.getElementById("rem-message")?.value.trim() || "";

  if (!recipient) {
    alert("Please provide a recipient phone number or email address.");
    return;
  }

  try {
    const res = await fetch("/delivery/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipient, channel, reminder_type, message }),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Failed to send reminder.");
      return;
    }
    closeSendReminderModal();
    loadDeliveryHistory();
    loadAnalyticsDashboard();
  } catch (err) {
    alert("Failed to send reminder: " + err.message);
  }
}

/* ══ INTERFACE PERSONALISATION (PROJ-401, PROJ-442, PROJ-443, PROJ-444) ══ */

let userPreferences = {
  theme: "dark",
  accent_color: "indigo",
  widget_order: ["stats", "analytics", "activity", "delivery", "escalations", "calendar"],
  widget_visibility: {
    stats: true,
    analytics: true,
    activity: true,
    delivery: true,
    escalations: true,
    calendar: true,
  },
};

async function initPersonalisation() {
  // Load from local storage first for fast render
  const cached = localStorage.getItem("user_settings");
  if (cached) {
    try {
      userPreferences = Object.assign(userPreferences, JSON.parse(cached));
      applySettingsToDOM(userPreferences);
    } catch (_) {}
  }

  // Sync with backend API (PROJ-444)
  try {
    const res = await fetch("/api/user/settings");
    if (res.ok) {
      const serverSettings = await res.json();
      userPreferences = Object.assign(userPreferences, serverSettings);
      localStorage.setItem("user_settings", JSON.stringify(userPreferences));
      applySettingsToDOM(userPreferences);
    }
  } catch (e) {
    console.warn("Could not sync preferences with server:", e);
  }
}

function applySettingsToDOM(prefs) {
  document.documentElement.setAttribute("data-theme", prefs.theme || "dark");
  document.documentElement.setAttribute("data-accent", prefs.accent_color || "indigo");

  // Widget visibility (PROJ-443)
  const vis = prefs.widget_visibility || {};
  const kpiEl = document.querySelector(".analytics-kpis");
  const trendEl = document.querySelector(".analytics-charts-grid");
  const actEl = document.getElementById("activity-feed");

  if (kpiEl) kpiEl.style.display = vis.analytics === false ? "none" : "grid";
  if (trendEl) trendEl.style.display = vis.analytics === false ? "none" : "grid";
}

function openPersonalisationModal() {
  const modal = document.getElementById("personalisation-modal");
  if (!modal) return;

  // Sync modal state with current preferences
  document.querySelectorAll(".theme-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-theme-val") === userPreferences.theme);
  });
  document.querySelectorAll(".accent-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-accent-val") === userPreferences.accent_color);
  });

  const vis = userPreferences.widget_visibility || {};
  const chkAnalytics = document.getElementById("pref-vis-analytics");
  const chkDelivery = document.getElementById("pref-vis-delivery");
  const chkActivity = document.getElementById("pref-vis-activity");
  const chkEscalations = document.getElementById("pref-vis-escalations");

  if (chkAnalytics) chkAnalytics.checked = vis.analytics !== false;
  if (chkDelivery) chkDelivery.checked = vis.delivery !== false;
  if (chkActivity) chkActivity.checked = vis.activity !== false;
  if (chkEscalations) chkEscalations.checked = vis.escalations !== false;

  modal.style.display = "flex";
}

function closePersonalisationModal() {
  const modal = document.getElementById("personalisation-modal");
  if (modal) modal.style.display = "none";
}

function selectTheme(theme) {
  userPreferences.theme = theme;
  document.querySelectorAll(".theme-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-theme-val") === theme);
  });
  document.documentElement.setAttribute("data-theme", theme);
}

function selectAccent(accent) {
  userPreferences.accent_color = accent;
  document.querySelectorAll(".accent-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-accent-val") === accent);
  });
  document.documentElement.setAttribute("data-accent", accent);
}

async function saveUserSettingsFromModal() {
  const vis = {
    analytics: document.getElementById("pref-vis-analytics")?.checked ?? true,
    delivery: document.getElementById("pref-vis-delivery")?.checked ?? true,
    activity: document.getElementById("pref-vis-activity")?.checked ?? true,
    escalations: document.getElementById("pref-vis-escalations")?.checked ?? true,
    calendar: true,
  };
  userPreferences.widget_visibility = vis;

  localStorage.setItem("user_settings", JSON.stringify(userPreferences));
  applySettingsToDOM(userPreferences);
  closePersonalisationModal();

  try {
    await fetch("/api/user/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(userPreferences),
    });
  } catch (e) {
    console.error("Failed to persist settings to server:", e);
  }
}

async function resetUserSettingsToDefault() {
  if (!confirm("Reset all interface preferences and themes back to factory defaults?")) return;
  try {
    const res = await fetch("/api/user/settings/reset", { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      userPreferences = data.settings;
      localStorage.setItem("user_settings", JSON.stringify(userPreferences));
      applySettingsToDOM(userPreferences);
      closePersonalisationModal();
    }
  } catch (e) {
    console.error("Failed to reset settings:", e);
  }
}

