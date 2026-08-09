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

// AI Receptionist tab
const receptionistArea  = document.getElementById("receptionist-area");
const receptionistInput = document.getElementById("receptionist-input");
const receptionistBtn   = document.getElementById("receptionist-btn");

// Knowledge Base tab (PROJ-279-283)
const kbFileInput    = document.getElementById("kb-file-input");
const kbUploadBtn    = document.getElementById("kb-upload-btn");
const kbSearchInput  = document.getElementById("kb-search-input");
const kbSearchBtn    = document.getElementById("kb-search-btn");
const kbSearchResults = document.getElementById("kb-search-results");
const kbDocList      = document.getElementById("kb-doc-list");
const kbErrorBox     = document.getElementById("kb-error");

let isLoading = false;
let activeTab = "shopping";
let activeLitMode = "search"; // "search" | "general" | "integrity"

// Auth (PROJ-349)
const authModal      = document.getElementById("auth-modal");
const authForm       = document.getElementById("auth-form");
const authUsername   = document.getElementById("auth-username");
const authPassword   = document.getElementById("auth-password");
const authError      = document.getElementById("auth-error");
const authSubmitBtn  = document.getElementById("auth-submit");
const authSubtitle   = document.getElementById("auth-subtitle");
const authSwitchText = document.getElementById("auth-switch-text");
const authSwitchLink = document.getElementById("auth-switch-link");
const userBadge      = document.getElementById("user-badge");
const logoutBtn      = document.getElementById("logout-btn");
let authMode = "login"; // "login" | "register"

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
   AUTH (PROJ-349) — login / register / logout, gates the rest of the UI
══════════════════════════════════════════════════════════ */

/** Check for a valid session cookie. Reveals the app on success,
 * shows the login modal on 401. Always resolves (never throws). */
async function checkAuth() {
  try {
    const res = await fetch(`${API_BASE}/auth/me`);
    if (res.ok) {
      const data = await res.json();
      onAuthed(data.username);
      return;
    }
  } catch { /* network error — fall through to login modal */ }
  showAuthModal();
}

function onAuthed(username) {
  document.body.classList.add("authed");
  authModal.style.display = "none";
  userBadge.style.display = "block";
  userBadge.textContent = username;
  logoutBtn.style.display = "block";
  loadHistory();
  loadKbDocuments();
}

function showAuthModal() {
  document.body.classList.remove("authed");
  authModal.style.display = "flex";
  authUsername.focus();
}

function setAuthMode(mode) {
  authMode = mode;
  authError.textContent = "";
  if (mode === "register") {
    authSubtitle.textContent = "Create an account to get started";
    authSubmitBtn.textContent = "Register";
    authSwitchText.textContent = "Already have an account?";
    authSwitchLink.textContent = "Log in";
    authPassword.autocomplete = "new-password";
  } else {
    authSubtitle.textContent = "Log in to continue";
    authSubmitBtn.textContent = "Log In";
    authSwitchText.textContent = "Don't have an account?";
    authSwitchLink.textContent = "Register";
    authPassword.autocomplete = "current-password";
  }
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const username = authUsername.value.trim();
  const password = authPassword.value;
  authError.textContent = "";
  authSubmitBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/auth/${authMode === "register" ? "register" : "login"}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      authError.textContent = data.detail || "Something went wrong. Try again.";
      return;
    }

    authPassword.value = "";
    onAuthed(data.username);
  } catch {
    authError.textContent = "Couldn't reach the server. Is it running?";
  } finally {
    authSubmitBtn.disabled = false;
  }
}

async function handleLogout() {
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: "POST" });
  } catch { /* ignore — clearing local UI state either way */ }
  document.body.classList.remove("authed");
  userBadge.style.display = "none";
  logoutBtn.style.display = "none";
  historyList.innerHTML = "";
  authUsername.value = "";
  authPassword.value = "";
  setAuthMode("login");
  showAuthModal();
}

/* ══════════════════════════════════════════════════════════
   INIT
══════════════════════════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", () => {
  checkStatus();
  checkAuth(); // shows the login modal, or reveals the app + loads history

  authForm.addEventListener("submit", handleAuthSubmit);
  authSwitchLink.addEventListener("click", e => {
    e.preventDefault();
    setAuthMode(authMode === "login" ? "register" : "login");
  });
  logoutBtn.addEventListener("click", handleLogout);

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

  // AI Receptionist input — Enter to send
  receptionistInput.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); sendReceptionistQuery(); }
  });
  receptionistBtn.addEventListener("click", sendReceptionistQuery);

  // Knowledge Base tab (PROJ-279-283)
  if (kbUploadBtn) kbUploadBtn.addEventListener("click", uploadKbFile);
  if (kbSearchBtn) kbSearchBtn.addEventListener("click", searchKb);
  if (kbSearchInput) kbSearchInput.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); searchKb(); }
  });
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
  if (tabName === "kb") loadKbDocuments();
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
   AI RECEPTIONIST TAB — POST /receptionist (PROJ-195, PROJ-209-218)
══════════════════════════════════════════════════════════ */
async function sendReceptionistQuery() {
  const message = receptionistInput.value.trim();
  if (!message || isLoading) return;

  appendUserMsg(receptionistArea, message, []);
  receptionistInput.value = "";
  setLoading(true, receptionistBtn, receptionistInput);
  const typingId = showTyping(receptionistArea);

  try {
    const res = await fetch(`${API_BASE}/receptionist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    removeTyping(typingId);

    if (res.status === 401) {
      appendErrorMsg(receptionistArea, "You've been logged out — please log in again.");
      showAuthModal();
      return;
    }
    if (!res.ok) throw new Error(`Server error: ${res.status}`);

    const data = await res.json();
    appendAgentBubble(receptionistArea, data.answer, [], "receptionist");
  } catch (err) {
    removeTyping(typingId);
    appendErrorMsg(receptionistArea, err.message);
  } finally {
    setLoading(false, receptionistBtn, receptionistInput);
    scrollToBottom(receptionistArea);
  }
}

function prefillReceptionist(text) {
  receptionistInput.value = text;
  receptionistInput.focus();
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
    : type === "receptionist" ? "AI Receptionist"
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

/* ══════════════════════════════════════════════════════════
   KNOWLEDGE BASE TAB — /kb/upload, /kb/list, /kb/{id}, /kb/search
   (PROJ-279-283)
══════════════════════════════════════════════════════════ */
function kbShowError(message) {
  if (!kbErrorBox) return;
  kbErrorBox.textContent = message;
  kbErrorBox.style.display = message ? "block" : "none";
}

async function loadKbDocuments() {
  if (!kbDocList) return;
  try {
    const res = await fetch(`${API_BASE}/kb/list`);
    if (res.status === 401) return; // not logged in yet — auth modal already showing
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    renderKbDocuments(data.documents || []);
  } catch (err) {
    kbShowError(`Couldn't load documents: ${err.message}`);
  }
}

function renderKbDocuments(documents) {
  if (documents.length === 0) {
    kbDocList.innerHTML = `<div class="kb-empty">No documents uploaded yet.</div>`;
    return;
  }
  kbDocList.innerHTML = documents.map(doc => `
    <div class="kb-doc-item" data-doc-id="${doc.id}">
      <div class="kb-doc-meta">
        <div class="kb-doc-name">${escHtml(doc.filename)}</div>
        <div class="kb-doc-sub">${(doc.size_bytes / 1024).toFixed(1)} KB · uploaded ${new Date(doc.uploaded_at).toLocaleString()}</div>
      </div>
      <button class="kb-doc-delete-btn" onclick="deleteKbDocument(${doc.id})">Delete</button>
    </div>
  `).join("");
}

async function uploadKbFile() {
  kbShowError("");
  const file = kbFileInput?.files?.[0];
  if (!file) {
    kbShowError("Choose a file first.");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);

  kbUploadBtn.disabled = true;
  kbUploadBtn.textContent = "Uploading…";
  try {
    const res = await fetch(`${API_BASE}/kb/upload`, { method: "POST", body: formData });
    if (res.status === 401) {
      kbShowError("You've been logged out — please log in again.");
      showAuthModal();
      return;
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Server error: ${res.status}`);
    kbFileInput.value = "";
    await loadKbDocuments();
  } catch (err) {
    kbShowError(err.message);
  } finally {
    kbUploadBtn.disabled = false;
    kbUploadBtn.textContent = "Upload ↑";
  }
}

async function deleteKbDocument(docId) {
  kbShowError("");
  try {
    const res = await fetch(`${API_BASE}/kb/${docId}`, { method: "DELETE" });
    if (res.status === 401) {
      kbShowError("You've been logged out — please log in again.");
      showAuthModal();
      return;
    }
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    await loadKbDocuments();
  } catch (err) {
    kbShowError(`Couldn't delete document: ${err.message}`);
  }
}

async function searchKb() {
  const query = kbSearchInput.value.trim();
  if (!query) return;
  kbSearchResults.innerHTML = `<div class="kb-no-results">Searching…</div>`;
  try {
    const res = await fetch(`${API_BASE}/kb/search?q=${encodeURIComponent(query)}`);
    if (res.status === 401) {
      showAuthModal();
      return;
    }
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    renderKbSearchResults(data.results || []);
  } catch (err) {
    kbSearchResults.innerHTML = `<div class="kb-no-results">Error: ${escHtml(err.message)}</div>`;
  }
}

function renderKbSearchResults(results) {
  if (results.length === 0) {
    kbSearchResults.innerHTML = `<div class="kb-no-results">No matching documents.</div>`;
    return;
  }
  kbSearchResults.innerHTML = results.map(r => `
    <div class="kb-result">
      <div class="kb-result-title">
        <span>${escHtml(r.filename)}</span>
        <span class="kb-result-score">${Math.round(r.score * 100)}% match</span>
      </div>
      <div class="kb-result-snippet">${escHtml(r.snippet)}</div>
    </div>
  `).join("");
}
