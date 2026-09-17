"""
app.web.reminders_list — reminders list view (PROJ-438).

Served at /reminders. Filter, search, and status, per the ticket.

Design decisions worth knowing:
  - ONE filter row above the table, scoping everything below it. Per-row or
    per-section filters are the documented anti-pattern.
  - A table, not a chart. This is identity-bearing tabular data that people
    need to read and act on individually.
  - Status is a badge with a coloured dot AND a word. Status colour never
    carries meaning alone — that is the rule for the reserved status palette,
    and it also happens to be what makes the list readable in grayscale.
  - Two distinct empty states: "you have no reminders" and "none match these
    filters". Collapsing them into one message is how people conclude their
    data is gone.
  - Filters are reflected in the URL, so a filtered view is shareable and the
    back button behaves.
"""

LIST_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reminders — Agent Factory</title>
<style>
  body {
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
    --critical:       #d03b3b;
    --warning:        #fab219;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) body {
      color-scheme: dark;
      --surface-1: #1a1a19; --page: #0d0d0d;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
      --hairline: #2c2c2a; --border: rgba(255,255,255,0.10);
      --accent: #3987e5; --good: #0ca30c; --critical: #e66767;
    }
  }
  :root[data-theme="dark"] body {
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --hairline: #2c2c2a; --border: rgba(255,255,255,0.10);
    --accent: #3987e5; --good: #0ca30c; --critical: #e66767;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--page); color: var(--text-primary);
    font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  .wrap { max-width: 1000px; margin: 0 auto; padding: 26px 22px 60px; }

  .crumb { font-size: 13px; margin-bottom: 14px; }
  .crumb a { color: var(--accent); text-decoration: none; }
  .crumb a:hover { text-decoration: underline; }

  .head { display: flex; align-items: baseline; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
  h1 { font-size: 21px; margin: 0; }
  .count { color: var(--text-secondary); font-size: 13px; }
  .newbtn {
    padding: 8px 15px; border-radius: 7px; border: 0; font: inherit; font-weight: 600;
    background: var(--accent); color: #fff; text-decoration: none; font-size: 14px;
  }

  .banner {
    display: flex; gap: 10px; align-items: flex-start;
    background: var(--surface-1); border: 1px solid var(--border);
    border-left: 3px solid var(--warning); border-radius: 8px;
    padding: 10px 13px; margin: 16px 0; font-size: 13px; color: var(--text-secondary);
  }
  .banner .ico { flex: none; font-weight: 700; color: var(--text-primary); }
  .banner b { color: var(--text-primary); font-weight: 600; }

  /* ── One filter row, scoping the whole table below it ──── */
  .filters {
    display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end;
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 10px; padding: 13px 15px; margin: 16px 0 18px;
  }
  .fgroup { display: flex; flex-direction: column; gap: 4px; }
  .fgroup label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
                  color: var(--text-secondary); font-weight: 600; }
  .fgroup.grow { flex: 1 1 220px; }
  input[type=search], select {
    padding: 8px 10px; font: inherit; font-size: 14px;
    color: var(--text-primary); background: var(--page);
    border: 1px solid var(--border); border-radius: 7px; width: 100%;
  }
  input:focus, select:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  .clear {
    background: transparent; border: 1px solid var(--border); border-radius: 7px;
    color: var(--text-secondary); font: inherit; font-size: 13px;
    padding: 8px 12px; cursor: pointer;
  }

  /* ── Table ──────────────────────────────────────────────── */
  .card {
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 10px; overflow: hidden;
  }
  table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th, td { text-align: left; padding: 11px 14px; border-bottom: 1px solid var(--hairline); }
  tbody tr:last-child td { border-bottom: 0; }
  th {
    color: var(--text-secondary); font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: .06em;
    background: var(--page);
  }
  tbody tr:hover { background: var(--page); }
  td.due { font-variant-numeric: tabular-nums; white-space: nowrap; }
  td.title a { color: var(--text-primary); text-decoration: none; font-weight: 500; }
  td.title a:hover { text-decoration: underline; }
  td.title .notes { color: var(--text-secondary); font-size: 12.5px; }
  td.actions { text-align: right; white-space: nowrap; }
  td.actions a { color: var(--accent); text-decoration: none; font-size: 13px; }
  td.actions a:hover { text-decoration: underline; }

  /* Status: coloured dot AND a word. Never colour alone. */
  .badge {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 13px; white-space: nowrap;
  }
  .badge .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .badge.scheduled .dot { background: var(--accent); }
  .badge.sent      .dot { background: var(--good); }
  .badge.failed    .dot { background: var(--critical); }
  .badge.cancelled .dot { background: var(--text-muted); }
  .overdue { color: var(--text-primary); font-size: 12px; }
  .overdue .mark { color: var(--critical); font-weight: 700; }

  .empty { padding: 34px 20px; text-align: center; color: var(--text-secondary); }
  .empty h3 { margin: 0 0 6px; font-size: 15px; color: var(--text-primary); }
  .empty p { margin: 0 0 14px; font-size: 13.5px; }
  .empty a { color: var(--accent); }
</style>
</head>
<body>
<div class="wrap">
  <div class="crumb"><a href="/dashboard">&larr; Dashboard</a></div>

  <div class="head">
    <div>
      <h1>Reminders</h1>
      <div class="count" id="count">Loading…</div>
    </div>
    <a class="newbtn" href="/reminders/new">New reminder</a>
  </div>

  <div class="banner">
    <span class="ico" aria-hidden="true">!</span>
    <div>
      <b>Provisional store.</b> These come from a local JSON file, not the real
      reminders store (<b>PROJ-422</b>). Nothing sends — the Reminders Engine is
      <b>PROJ-395</b>, so no reminder will ever reach status <i>sent</i> yet.
    </div>
  </div>

  <div class="filters" role="search">
    <div class="fgroup grow">
      <label for="q">Search</label>
      <input type="search" id="q" placeholder="Title or notes…" autocomplete="off">
    </div>
    <div class="fgroup">
      <label for="status">Status</label>
      <select id="status">
        <option value="">All</option>
        <option value="scheduled">Scheduled</option>
        <option value="sent">Sent</option>
        <option value="cancelled">Cancelled</option>
        <option value="failed">Failed</option>
      </select>
    </div>
    <div class="fgroup">
      <label for="channel">Channel</label>
      <select id="channel">
        <option value="">All</option>
        <option value="telegram">Telegram</option>
        <option value="email">Email</option>
        <option value="sms">SMS</option>
      </select>
    </div>
    <div class="fgroup">
      <label for="sort">Sort</label>
      <select id="sort">
        <option value="due_asc">Due — soonest</option>
        <option value="due_desc">Due — latest</option>
        <option value="created_desc">Newest first</option>
        <option value="title_asc">Title A–Z</option>
      </select>
    </div>
    <button type="button" class="clear" id="clear">Clear filters</button>
  </div>

  <div class="card" id="card">
    <div class="empty"><p>Loading…</p></div>
  </div>
</div>

<script>
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

const els = {
  q: document.getElementById("q"),
  status: document.getElementById("status"),
  channel: document.getElementById("channel"),
  sort: document.getElementById("sort"),
  card: document.getElementById("card"),
  count: document.getElementById("count"),
};

const STATUS_LABEL = {
  scheduled: "Scheduled", sent: "Sent", cancelled: "Cancelled", failed: "Failed",
};
const CHANNEL_LABEL = { telegram: "Telegram", email: "Email", sms: "SMS" };

function fmtDue(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

// Read filters from the URL so a shared link opens the same view.
function readUrl() {
  const p = new URLSearchParams(location.search);
  els.q.value = p.get("q") || "";
  els.status.value = p.get("status") || "";
  els.channel.value = p.get("channel") || "";
  els.sort.value = p.get("sort") || "due_asc";
}

function currentParams() {
  const p = new URLSearchParams();
  if (els.q.value.trim()) p.set("q", els.q.value.trim());
  if (els.status.value) p.set("status", els.status.value);
  if (els.channel.value) p.set("channel", els.channel.value);
  if (els.sort.value && els.sort.value !== "due_asc") p.set("sort", els.sort.value);
  return p;
}

function anyFilterActive() {
  return !!(els.q.value.trim() || els.status.value || els.channel.value);
}

function row(r) {
  const overdue = r.status === "scheduled" && new Date(r.due_at) < new Date();
  const editUrl = "/reminders/" + encodeURIComponent(r.id) + "/edit";
  return `
    <tr>
      <td class="title">
        <a href="${editUrl}">${esc(r.title)}</a>
        ${r.notes ? `<div class="notes">${esc(r.notes.slice(0, 90))}${r.notes.length > 90 ? "…" : ""}</div>` : ""}
      </td>
      <td class="due">${esc(fmtDue(r.due_at))}
        ${overdue ? `<div class="overdue"><span class="mark" aria-hidden="true">!</span> Overdue — will not send</div>` : ""}
      </td>
      <td>${esc(CHANNEL_LABEL[r.channel] || r.channel)}</td>
      <td>
        <span class="badge ${esc(r.status)}">
          <span class="dot" aria-hidden="true"></span>${esc(STATUS_LABEL[r.status] || r.status)}
        </span>
      </td>
      <td class="actions"><a href="${editUrl}">Edit</a></td>
    </tr>`;
}

function renderEmpty(unfilteredTotal) {
  // Two genuinely different situations. Collapsing them is how people
  // conclude their data has disappeared.
  if (unfilteredTotal === 0) {
    els.card.innerHTML = `
      <div class="empty">
        <h3>No reminders yet</h3>
        <p>Create one and it will show up here.</p>
        <a href="/reminders/new">New reminder</a>
      </div>`;
  } else {
    els.card.innerHTML = `
      <div class="empty">
        <h3>Nothing matches these filters</h3>
        <p>${unfilteredTotal} reminder${unfilteredTotal === 1 ? "" : "s"} exist${unfilteredTotal === 1 ? "s" : ""}, but none match what you have selected.</p>
        <a href="#" id="clearinline">Clear filters</a>
      </div>`;
    const link = document.getElementById("clearinline");
    if (link) link.onclick = ev => { ev.preventDefault(); clearFilters(); };
  }
}

let seq = 0;
async function load() {
  const mine = ++seq;
  const params = currentParams();

  // Keep the URL in step without stacking history entries per keystroke.
  const qs = params.toString();
  history.replaceState(null, "", qs ? "?" + qs : location.pathname);

  try {
    const r = await fetch("/api/reminders" + (qs ? "?" + qs : ""));
    // A slower earlier request must not overwrite a newer result.
    if (mine !== seq) return;

    if (r.status === 422) {
      const d = await r.json().catch(() => ({}));
      els.card.innerHTML = `<div class="empty"><h3>Invalid filter</h3><p>${
        esc(Object.values(d.errors || {}).join(" "))}</p></div>`;
      els.count.textContent = "";
      return;
    }
    if (!r.ok) throw new Error("HTTP " + r.status);

    const d = await r.json();
    if (mine !== seq) return;

    if (!d.reminders.length) {
      renderEmpty(d.unfiltered_total);
      els.count.textContent = anyFilterActive()
        ? `0 of ${d.unfiltered_total}`
        : "None yet";
      return;
    }

    els.card.innerHTML = `
      <table>
        <thead>
          <tr><th>Title</th><th>Due</th><th>Channel</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>${d.reminders.map(row).join("")}</tbody>
      </table>`;

    els.count.textContent = (d.total === d.unfiltered_total)
      ? `${d.total} reminder${d.total === 1 ? "" : "s"}`
      : `${d.total} of ${d.unfiltered_total} match`;
  } catch (err) {
    if (mine !== seq) return;
    els.card.innerHTML = `<div class="empty"><h3>Could not load reminders</h3><p>${esc(err.message)}</p></div>`;
    els.count.textContent = "";
  }
}

function clearFilters() {
  els.q.value = "";
  els.status.value = "";
  els.channel.value = "";
  els.sort.value = "due_asc";
  load();
}

// Debounce typing; fire selects immediately.
let t = null;
els.q.addEventListener("input", () => {
  clearTimeout(t);
  t = setTimeout(load, 250);
});
["status", "channel", "sort"].forEach(k => els[k].addEventListener("change", load));
document.getElementById("clear").onclick = clearFilters;
window.addEventListener("popstate", () => { readUrl(); load(); });

readUrl();
load();
</script>
</body>
</html>
"""
