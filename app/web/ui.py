"""
app.web.ui — minimal web UI with a skills sidebar (PROJ-334..338).

Served at /ui. A single self-contained HTML document with no build step and
no CDN: the deployment target is a Mac on a home connection, and a UI that
breaks when a CDN is unreachable is worse than a plain one that always works.

The sidebar is populated at runtime from GET /skills, so adding a manifest to
skills/manifests/ makes it appear here with no change to this file.
"""

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Factory</title>
<style>
  :root {
    --bg: #12131a;
    --panel: #1a1c25;
    --panel-2: #21242f;
    --line: #2e3240;
    --text: #e6e8ef;
    --muted: #9aa1b4;
    --accent: #6ea8fe;
    --ok: #4ec9a5;
    --warn: #e0a458;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg: #f6f7fa; --panel: #ffffff; --panel-2: #f0f2f7; --line: #dfe3ec;
      --text: #1b1e28; --muted: #5c6478; --accent: #2563eb;
      --ok: #0f9b74; --warn: #b26b16;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  .layout { display: grid; grid-template-columns: 300px 1fr; min-height: 100vh; }
  @media (max-width: 820px) { .layout { grid-template-columns: 1fr; } }

  aside {
    background: var(--panel); border-right: 1px solid var(--line);
    padding: 20px 16px; overflow-y: auto;
  }
  aside h1 { font-size: 15px; margin: 0 0 4px; letter-spacing: .01em; }
  aside .ver { color: var(--muted); font-size: 12px; margin-bottom: 18px; }
  .sec { color: var(--muted); font-size: 11px; text-transform: uppercase;
         letter-spacing: .08em; margin: 18px 0 8px; }

  .skill {
    background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px;
    padding: 10px 12px; margin-bottom: 10px; cursor: pointer;
  }
  .skill:hover { border-color: var(--accent); }
  .skill .row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .skill .nm { font-weight: 600; }
  .skill .vr { color: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
  .skill .ds { color: var(--muted); font-size: 12px; margin-top: 4px; }
  .tools { margin-top: 8px; display: none; }
  .skill.open .tools { display: block; }
  .tool { font-size: 12px; padding: 4px 0; border-top: 1px solid var(--line); }
  .tool code { color: var(--accent); }
  .tool .td { color: var(--muted); display: block; margin-top: 2px; }

  main { padding: 28px 32px; max-width: 900px; }
  h2 { margin: 0 0 16px; font-size: 20px; }
  form { display: flex; gap: 8px; margin-bottom: 20px; }
  input[type=text] {
    flex: 1; padding: 11px 13px; border-radius: 8px;
    border: 1px solid var(--line); background: var(--panel); color: var(--text); font: inherit;
  }
  input[type=text]:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  button {
    padding: 11px 20px; border-radius: 8px; border: 0;
    background: var(--accent); color: #fff; font: inherit; font-weight: 600; cursor: pointer;
  }
  button:disabled { opacity: .55; cursor: default; }

  #out {
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 18px 20px; white-space: pre-wrap; word-break: break-word; min-height: 90px;
  }
  .muted { color: var(--muted); }
  .err { color: var(--warn); }
  .badge {
    display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 999px;
    border: 1px solid var(--line); color: var(--muted); margin-left: 6px;
  }
  .badge.on { color: var(--ok); border-color: var(--ok); }
</style>
</head>
<body>
<div class="layout">
  <aside>
    <h1>Agent Factory</h1>
    <div class="ver" id="ver">loading…</div>
    <div class="sec">Skills</div>
    <div id="skills" class="muted">loading…</div>
  </aside>

  <main>
    <h2>Ask</h2>
    <form id="f">
      <input type="text" id="q" placeholder="Find papers on transformer architecture"
             autocomplete="off" required>
      <button type="submit" id="go">Send</button>
    </form>
    <div id="out" class="muted">Results appear here.</div>
  </main>
</div>

<script>
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function loadSkills() {
  const box = document.getElementById("skills");
  try {
    const r = await fetch("/skills");
    const d = await r.json();

    if (!d.skills || !d.skills.length) {
      box.textContent = "No skills registered.";
      return;
    }

    box.innerHTML = "";
    for (const s of d.skills) {
      const el = document.createElement("div");
      el.className = "skill";
      const tools = (s.tools || []).map(t =>
        `<div class="tool"><code>${esc(t.name)}</code>
           <span class="td">${esc(t.description).slice(0, 110)}…</span></div>`).join("");
      el.innerHTML =
        `<div class="row"><span class="nm">${esc(s.displayName || s.name)}</span>
           <span class="vr">v${esc(s.version)}</span></div>
         <div class="ds">${esc(s.description).slice(0, 120)}…</div>
         <div class="tools">${tools}</div>`;
      // Click to expand rather than showing everything at once — with 4 tools
      // per skill the sidebar is unreadable fully expanded.
      el.onclick = () => el.classList.toggle("open");
      box.appendChild(el);
    }

    // Surface malformed manifests instead of quietly dropping them.
    if (d.errors && d.errors.length) {
      const e = document.createElement("div");
      e.className = "err";
      e.style.fontSize = "12px";
      e.textContent = `${d.errors.length} manifest(s) failed to load — see /skills`;
      box.appendChild(e);
    }
  } catch (err) {
    box.innerHTML = `<span class="err">Could not load skills: ${esc(err.message)}</span>`;
  }
}

async function loadHealth() {
  try {
    const d = await (await fetch("/health")).json();
    const ok = d.status === "ok";
    document.getElementById("ver").innerHTML =
      `v${esc(d.version)} <span class="badge ${ok ? "on" : ""}">${esc(d.status)}</span>`;
  } catch {
    document.getElementById("ver").innerHTML = `<span class="err">offline</span>`;
  }
}

document.getElementById("f").onsubmit = async ev => {
  ev.preventDefault();
  const q = document.getElementById("q").value.trim();
  if (!q) return;

  const out = document.getElementById("out");
  const go = document.getElementById("go");
  go.disabled = true;
  out.className = "muted";
  out.textContent = "Working…";

  try {
    const r = await fetch("/query", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({query: q}),
    });
    const d = await r.json();

    if (!r.ok) {
      out.className = "err";
      // 503 means unconfigured, not broken — say which.
      out.textContent = (r.status === 503 ? "Not configured: " : `Error ${r.status}: `)
                        + (d.detail || "request failed");
      return;
    }

    out.className = "";
    let text = d.summary || "(no summary)";
    if (d.results && d.results.length) {
      text += `\\n\\n— ${d.results.length} result(s) via ${d.skill} in ${d.duration}s —\\n`;
      for (const it of d.results.slice(0, 10)) {
        text += `\\n• ${it.title || "(untitled)"}`;
        if (it.year) text += ` (${it.year})`;
        if (it.price) text += ` — ${it.price}`;
        if (it.rating) text += ` — ${it.rating}`;
        if (it.link) text += `\\n  ${it.link}`;
      }
    }
    out.textContent = text;
  } catch (err) {
    out.className = "err";
    out.textContent = "Request failed: " + err.message;
  } finally {
    go.disabled = false;
  }
};

loadHealth();
loadSkills();
</script>
</body>
</html>
"""
