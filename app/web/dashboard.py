"""
app.web.dashboard — dashboard shell: KPI counters and nav (PROJ-437).

Served at /dashboard. One self-contained document, no build step and no CDN —
same reasoning as app/web/ui.py: the deployment target is a Mac on a home
connection, and a UI that breaks when a CDN is unreachable is worse than a
plain one that always works.

Form choices, per the project data-viz guidance:
  - Headline numbers are a KPI ROW OF STAT TILES, not charts. A one-bar bar
    chart for "contacts: 42" is the classic mistake.
  - Exactly ONE hero figure (upcoming reminders — what the epic says the page
    leads with), >=48px, in the same system sans as everything else.
  - Values use proportional figures; tabular-nums is reserved for columns that
    align vertically, where equal-width digits actually help.
  - Text wears text tokens only. No value or label is painted in an accent
    colour; identity comes from a mark beside the text.
  - No sparklines yet: a trend line needs history, and the reminders store
    (PROJ-422) does not exist. The tile contract leaves room for them.

Colours are the reference palette's tokens, declared once as custom properties
for light and dark. Dark mode is a selected set of steps, not an inverted flip,
and is declared under both the media query and the [data-theme] scope so a
manual toggle wins either way.
"""

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard — Agent Factory</title>
<style>
  .viz-root, body {
    color-scheme: light;
    --surface-1:      #fcfcfb;
    --page:           #f9f9f7;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --text-muted:     #898781;
    --hairline:       #e1e0d9;
    --border:         rgba(11,11,11,0.10);
    --accent:         #2a78d6;
    --good:           #0ca30c;
    --warning:        #fab219;
    --delta-up-good:  #006300;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) body {
      color-scheme: dark;
      --surface-1:      #1a1a19;
      --page:           #0d0d0d;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted:     #898781;
      --hairline:       #2c2c2a;
      --border:         rgba(255,255,255,0.10);
      --accent:         #3987e5;
      --good:           #0ca30c;
      --warning:        #fab219;
      --delta-up-good:  #0ca30c;
    }
  }
  :root[data-theme="dark"] body {
    color-scheme: dark;
    --surface-1:      #1a1a19;
    --page:           #0d0d0d;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted:     #898781;
    --hairline:       #2c2c2a;
    --border:         rgba(255,255,255,0.10);
    --accent:         #3987e5;
    --delta-up-good:  #0ca30c;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--page);
    color: var(--text-primary);
    font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }

  .layout { display: grid; grid-template-columns: 232px 1fr; min-height: 100vh; }
  @media (max-width: 860px) { .layout { grid-template-columns: 1fr; } }

  /* ── Nav ─────────────────────────────────────────────── */
  nav {
    background: var(--surface-1);
    border-right: 1px solid var(--border);
    padding: 22px 14px;
  }
  .brand { font-size: 14px; font-weight: 650; letter-spacing: .01em; padding: 0 8px; }
  .brand .sub { display: block; color: var(--text-muted); font-size: 12px; font-weight: 400; margin-top: 2px; }
  .navsec {
    color: var(--text-muted); font-size: 11px; text-transform: uppercase;
    letter-spacing: .08em; margin: 22px 8px 8px;
  }
  nav a {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    padding: 7px 8px; margin-bottom: 2px; border-radius: 6px;
    color: var(--text-secondary); text-decoration: none; font-size: 14px;
  }
  nav a:hover { background: var(--page); color: var(--text-primary); }
  nav a[aria-current="page"] {
    background: var(--page); color: var(--text-primary); font-weight: 600;
    /* A 2px accent mark beside the label, not coloured text. */
    box-shadow: inset 2px 0 0 var(--accent);
  }
  nav a.pending { color: var(--text-muted); cursor: not-allowed; }
  .tag {
    font-size: 10px; letter-spacing: .04em; padding: 1px 6px; border-radius: 999px;
    border: 1px solid var(--border); color: var(--text-muted); white-space: nowrap;
  }

  /* ── Main ────────────────────────────────────────────── */
  main { padding: 26px 30px 48px; max-width: 1080px; }
  .head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  h1 { font-size: 21px; margin: 0 0 4px; }
  /* --text-muted measures 3.50:1 on the light surface — fine for axis/label
     chrome, which is what the palette reserves it for, but below AA's 4.5:1
     for text a reader must actually read. Anything load-bearing below
     (metric notes, empty-state explanations, the table's detail column)
     therefore uses secondary ink at 7.73:1. Muted is kept only for small
     uppercase section headings and tags, whose content is repeated elsewhere. */
  .head .when { color: var(--text-secondary); font-size: 12.5px; }

  /* ── Banner: icon + label, never colour alone ────────── */
  .banner {
    display: flex; gap: 10px; align-items: flex-start;
    background: var(--surface-1); border: 1px solid var(--border);
    border-left: 3px solid var(--warning);
    border-radius: 8px; padding: 11px 14px; margin: 18px 0 22px;
    font-size: 13.5px; color: var(--text-secondary);
  }
  .banner .ico { flex: none; font-weight: 700; color: var(--text-primary); }
  .banner b { color: var(--text-primary); font-weight: 600; }

  /* ── Hero figure — exactly one per view ──────────────── */
  .hero {
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 10px; padding: 20px 22px; margin-bottom: 14px;
  }
  .hero .label { color: var(--text-secondary); font-size: 13px; }
  .hero .value {
    font-size: 52px; line-height: 1.05; font-weight: 600; margin-top: 6px;
    /* Proportional figures: tabular-nums makes a big number look loose. */
    font-variant-numeric: proportional-nums;
  }
  .hero .value.none { font-size: 26px; font-weight: 500; color: var(--text-secondary); }
  .hero .meta { color: var(--text-secondary); font-size: 12.5px; margin-top: 8px; }

  /* ── KPI row of stat tiles ───────────────────────────── */
  .kpis {
    display: grid; gap: 14px; margin-bottom: 26px;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  }
  .tile {
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 10px; padding: 15px 16px;
  }
  .tile .label { color: var(--text-secondary); font-size: 12.5px; }
  .tile .value {
    font-size: 27px; font-weight: 600; margin-top: 5px;
    font-variant-numeric: proportional-nums;
  }
  .tile .value.none { font-size: 14px; font-weight: 500; color: var(--text-secondary); margin-top: 8px; }
  .tile .delta { font-size: 12px; margin-top: 4px; color: var(--text-secondary); }
  .tile .delta.up { color: var(--delta-up-good); }
  .tile .note { color: var(--text-secondary); font-size: 11.5px; margin-top: 7px; }
  .tile.pending { border-style: dashed; }

  /* ── Sections ────────────────────────────────────────── */
  .panels { display: grid; gap: 14px; grid-template-columns: 1fr 1fr; }
  @media (max-width: 760px) { .panels { grid-template-columns: 1fr; } }
  .panel {
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px 18px; min-height: 150px;
  }
  .panel h2 { font-size: 14px; margin: 0 0 3px; }
  .panel .hint { color: var(--text-secondary); font-size: 12.5px; margin-bottom: 12px; }
  .empty {
    border-top: 1px solid var(--hairline); padding-top: 12px;
    color: var(--text-secondary); font-size: 13px;
  }
  .empty code { color: var(--text-secondary); }

  /* ── Table view — every value reachable without hover ── */
  details.tableview { margin-top: 24px; }
  details.tableview summary {
    cursor: pointer; color: var(--text-secondary); font-size: 13px;
    padding: 6px 0;
  }
  table { border-collapse: collapse; width: 100%; margin-top: 10px; font-size: 13px; }
  th, td {
    text-align: left; padding: 7px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  th { color: var(--text-muted); font-weight: 500; font-size: 11.5px;
       text-transform: uppercase; letter-spacing: .05em; }
  /* Columns of numbers DO align vertically, so tabular here is correct. */
  td.num { font-variant-numeric: tabular-nums; }
  .muted { color: var(--text-secondary); }
</style>
</head>
<body>
<div class="layout">

  <nav>
    <div class="brand">Agent Factory<span class="sub">Sprint 4</span></div>

    <div class="navsec">Overview</div>
    <a href="/dashboard" aria-current="page">Dashboard</a>

    <div class="navsec">Manage</div>
    <a class="pending" aria-disabled="true" title="Blocked by PROJ-417">
      Contacts <span class="tag">PROJ-417</span>
    </a>
    <a href="/reminders/new">New reminder</a>
    <a class="pending" aria-disabled="true" title="Blocked by PROJ-438">
      Reminders list <span class="tag">PROJ-438</span>
    </a>
    <a class="pending" aria-disabled="true" title="Blocked by PROJ-440">
      Preferences <span class="tag">PROJ-440</span>
    </a>

    <div class="navsec">Agent</div>
    <a href="/ui">Ask</a>
    <a href="/skills">Skills API</a>
    <a href="/docs">API docs</a>
    <a href="/health">Health</a>
  </nav>

  <main>
    <div class="head">
      <div>
        <h1>Dashboard</h1>
        <div class="when" id="when">Loading…</div>
      </div>
    </div>

    <div class="banner" id="authbanner" hidden>
      <span class="ico" aria-hidden="true">!</span>
      <div>
        <b>Not authenticated.</b> This page is served without access control.
        Accounts and sign-in are <b>PROJ-392</b> (Accounts &amp; Multi-tenancy),
        which has not landed — so there is no org scoping and no session check yet.
        Do not expose this on a public URL.
      </div>
    </div>

    <section aria-labelledby="hero-label">
      <div class="hero" id="hero">
        <div class="label" id="hero-label">—</div>
        <div class="value none">Loading…</div>
      </div>
    </section>

    <section class="kpis" id="kpis" aria-label="Key metrics"></section>

    <div class="panels">
      <div class="panel">
        <h2>Upcoming reminders</h2>
        <div class="hint">Next scheduled sends, soonest first.</div>
        <div class="empty">
          The list view is <code>PROJ-438</code>. You can
          <a href="/reminders/new">create a reminder</a> now — it saves to the
          provisional local store until <code>PROJ-422</code> lands.
        </div>
      </div>
      <div class="panel">
        <h2>Recent history</h2>
        <div class="hint">What was sent, and what happened.</div>
        <div class="empty">
          Waiting on send history — <code>PROJ-422</code>.
        </div>
      </div>
    </div>

    <details class="tableview">
      <summary>Table view — all metrics</summary>
      <table>
        <thead>
          <tr><th>Metric</th><th>Value</th><th>Status</th><th>Detail</th></tr>
        </thead>
        <tbody id="tablebody"></tbody>
      </table>
    </details>
  </main>
</div>

<script>
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

// Auto-compact per the stat-tile contract: 1,284 / 12.9K / 4.2M
function compact(n) {
  if (typeof n !== "number" || !isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e9) return (n / 1e9).toFixed(1).replace(/\\.0$/, "") + "B";
  if (abs >= 1e6) return (n / 1e6).toFixed(1).replace(/\\.0$/, "") + "M";
  if (abs >= 10000) return (n / 1e3).toFixed(1).replace(/\\.0$/, "") + "K";
  return n.toLocaleString();
}

function tile(m) {
  const el = document.createElement("div");
  el.className = "tile" + (m.available ? "" : " pending");

  let body;
  if (m.available && m.value !== null) {
    body = `<div class="value">${esc(compact(m.value))}${m.unit ? " " + esc(m.unit) : ""}</div>`;
    // Delta only renders with a named period — a signed number alone says nothing.
    if (m.delta !== null && m.delta !== undefined && m.delta_period) {
      const good = m.higher_is_better ? m.delta > 0 : m.delta < 0;
      const sign = m.delta > 0 ? "+" : "";
      body += `<div class="delta${good ? " up" : ""}">${sign}${esc(compact(m.delta))} vs ${esc(m.delta_period)}</div>`;
    }
  } else {
    // Never render 0 for "no source yet" — it is indistinguishable from a
    // measured zero.
    body = `<div class="value none">Not available</div>`;
  }

  const note = !m.available && m.blocked_by
    ? `Blocked by ${esc(m.blocked_by)}. ${esc(m.note || "")}`
    : esc(m.note || "");

  el.innerHTML = `<div class="label">${esc(m.label)}</div>${body}` +
                 (note ? `<div class="note">${note}</div>` : "");
  return el;
}

async function load() {
  try {
    const r = await fetch("/api/stats");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();

    document.getElementById("authbanner").hidden = !!d.authenticated;

    const metrics = d.metrics || [];
    const hero = metrics.find(m => m.key === d.hero) || metrics[0];
    const rest = metrics.filter(m => m !== hero);

    // Hero
    if (hero) {
      const h = document.getElementById("hero");
      const val = (hero.available && hero.value !== null)
        ? `<div class="value">${esc(compact(hero.value))}</div>`
        : `<div class="value none">Not available</div>`;
      const meta = !hero.available && hero.blocked_by
        ? `Blocked by ${esc(hero.blocked_by)}. ${esc(hero.note || "")}`
        : esc(hero.note || "");
      h.innerHTML = `<div class="label" id="hero-label">${esc(hero.label)}</div>${val}` +
                    (meta ? `<div class="meta">${meta}</div>` : "");
    }

    // KPI row
    const box = document.getElementById("kpis");
    box.innerHTML = "";
    rest.forEach(m => box.appendChild(tile(m)));

    // Table view — same values, no hover required
    document.getElementById("tablebody").innerHTML = metrics.map(m => `
      <tr>
        <td>${esc(m.label)}</td>
        <td class="num">${m.available && m.value !== null ? esc(compact(m.value)) : '<span class="muted">—</span>'}</td>
        <td>${m.available ? "Live" : '<span class="muted">Pending</span>'}</td>
        <td class="muted">${m.blocked_by ? esc(m.blocked_by) + ". " : ""}${esc(m.note || "")}</td>
      </tr>`).join("");

    document.getElementById("when").textContent =
      `${d.available_count} of ${metrics.length} metrics live · updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    document.getElementById("when").textContent = "Could not load metrics: " + err.message;
  }
}

load();
</script>
</body>
</html>
"""
