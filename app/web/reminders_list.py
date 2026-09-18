"""
app.web.reminders_list — reminders list view (PROJ-438).

Rewritten onto the published contract (PROJ-404): search is over `message`,
the time column is `send_at`, the fourth status is `blocked` rather than
`cancelled`, and rows resolve their contact so the list shows who each
reminder is for.

Design points carried over from the first version, still true:
  - ONE filter row above the table, scoping everything below it.
  - A table, not a chart — identity-bearing rows people act on individually.
  - Status is a dot AND a word, never colour alone.
  - Two distinct empty states: "no reminders" vs "none match these filters".
  - Filters mirrored into the URL, so a view is shareable.

New here: a `blocked` row shows *why* it was blocked, and an overdue
`scheduled` row is called out as stuck rather than upcoming.
"""

from app.web.contacts_ui import ESC_JS, STYLE

LIST_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reminders — Agent Factory</title>__STYLE__</head>
<body><div class="wrap">
  <div class="crumb"><a href="/dashboard">&larr; Dashboard</a></div>
  <div class="head">
    <div><h1>Reminders</h1><div class="sub" id="count">Loading…</div></div>
    <a class="btn" href="/reminders/new">New reminder</a>
  </div>

  <div class="banner">
    <span class="ico" aria-hidden="true">!</span>
    <div><b>Nothing sends yet.</b> The Reminders Engine is <b>PROJ-395</b>, so
    no reminder will reach <i>sent</i>. Consent is still enforced at send time
    (<b>PROJ-441</b>) — a reminder can already be seen as blocked before its
    send time arrives.</div>
  </div>

  <div class="filters" role="search">
    <div class="fgroup grow"><label for="q">Search</label>
      <input type="search" id="q" placeholder="Message text…" autocomplete="off"></div>
    <div class="fgroup"><label for="status">Status</label>
      <select id="status">
        <option value="">All</option>
        <option value="scheduled">Scheduled</option>
        <option value="sent">Sent</option>
        <option value="blocked">Blocked</option>
        <option value="failed">Failed</option>
      </select></div>
    <div class="fgroup"><label for="contact">Contact</label>
      <select id="contact"><option value="">All</option></select></div>
    <div class="fgroup"><label for="sort">Sort</label>
      <select id="sort">
        <option value="send_at_asc">Send — soonest</option>
        <option value="send_at_desc">Send — latest</option>
        <option value="created_desc">Newest first</option>
        <option value="message_asc">Message A–Z</option>
      </select></div>
    <button type="button" class="btn ghost" id="clear">Clear</button>
  </div>

  <div class="card" id="card"><div class="empty">Loading…</div></div>
</div>
<script>__ESC__
const STATUS_LABEL = {scheduled:"Scheduled", sent:"Sent", blocked:"Blocked", failed:"Failed"};
const els = {
  q: document.getElementById("q"), status: document.getElementById("status"),
  contact: document.getElementById("contact"), sort: document.getElementById("sort"),
  card: document.getElementById("card"), count: document.getElementById("count"),
};
let BY_ID = {};

function fmt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? esc(iso) : d.toLocaleString(undefined,
    {year:"numeric", month:"short", day:"2-digit", hour:"2-digit", minute:"2-digit"});
}

function readUrl() {
  const p = new URLSearchParams(location.search);
  els.q.value = p.get("q") || "";
  els.status.value = p.get("status") || "";
  els.contact.value = p.get("contact_id") || "";
  els.sort.value = p.get("sort") || "send_at_asc";
}
function params() {
  const p = new URLSearchParams();
  if (els.q.value.trim()) p.set("q", els.q.value.trim());
  if (els.status.value) p.set("status", els.status.value);
  if (els.contact.value) p.set("contact_id", els.contact.value);
  if (els.sort.value && els.sort.value !== "send_at_asc") p.set("sort", els.sort.value);
  return p;
}
function filtered() { return !!(els.q.value.trim() || els.status.value || els.contact.value); }

async function loadContacts() {
  try {
    const d = await (await fetch("/api/contacts")).json();
    BY_ID = Object.fromEntries((d.contacts || []).map(c => [String(c.id), c]));
    els.contact.innerHTML = `<option value="">All</option>` + (d.contacts || []).map(c =>
      `<option value="${esc(String(c.id))}">${esc(c.name || c.phone_number)}</option>`).join("");
  } catch (err) { /* the list still works without the contact filter */ }
}

function row(r) {
  const c = BY_ID[String(r.contact_id)];
  const who = c ? (c.name || c.phone_number) : `#${r.contact_id}`;
  const overdue = r.status === "scheduled" && new Date(r.send_at) < new Date();
  const edit = "/reminders/" + encodeURIComponent(r.id) + "/edit";
  return `<tr>
    <td><a href="${edit}">${esc((r.message || "").slice(0, 80))}${
      (r.message || "").length > 80 ? "…" : ""}</a></td>
    <td>${c ? `<a href="/contacts/${esc(String(c.id))}">${esc(who)}</a>` : esc(who)}</td>
    <td class="num">${fmt(r.send_at)}${
      overdue ? `<div class="sub" style="color:var(--text-primary)">
        <span style="color:var(--critical);font-weight:700">!</span> Overdue — stuck, will not send</div>` : ""}</td>
    <td><span class="badge ${esc(r.status)}"><span class="dot" aria-hidden="true"></span>${
      esc(STATUS_LABEL[r.status] || r.status)}</span>${
      r.blocked_reason ? `<div class="sub">${esc(r.blocked_reason)}</div>` : ""}${
      r.sent_at ? `<div class="sub">${fmt(r.sent_at)}</div>` : ""}</td>
    <td class="actions"><a href="${edit}">Edit</a></td></tr>`;
}

function renderEmpty(unfilteredTotal) {
  if (unfilteredTotal === 0) {
    els.card.innerHTML = `<div class="empty"><h3>No reminders yet</h3>
      <p>Schedule one and it will show up here.</p>
      <a class="btn" href="/reminders/new">New reminder</a></div>`;
  } else {
    els.card.innerHTML = `<div class="empty"><h3>Nothing matches these filters</h3>
      <p>${unfilteredTotal} reminder${unfilteredTotal === 1 ? "" : "s"} exist, but none match.</p>
      <a href="#" id="ci">Clear filters</a></div>`;
    const ci = document.getElementById("ci");
    if (ci) ci.onclick = e => { e.preventDefault(); clearAll(); };
  }
}

let seq = 0;
async function load() {
  const mine = ++seq;
  const qs = params().toString();
  history.replaceState(null, "", qs ? "?" + qs : location.pathname);
  try {
    const r = await fetch("/api/reminders" + (qs ? "?" + qs : ""));
    if (mine !== seq) return;
    if (r.status === 422) {
      const d = await r.json().catch(() => ({}));
      els.card.innerHTML = `<div class="empty"><h3>Invalid filter</h3><p>${
        esc(Object.values(d.errors || {}).join(" "))}</p></div>`;
      els.count.textContent = ""; return;
    }
    if (!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();
    if (mine !== seq) return;

    if (!d.reminders.length) {
      renderEmpty(d.unfiltered_total);
      els.count.textContent = filtered() ? `0 of ${d.unfiltered_total}` : "None yet";
      return;
    }
    els.card.innerHTML = `<table><thead><tr>
        <th>Message</th><th>Contact</th><th>Send at</th><th>Status</th><th></th>
      </tr></thead><tbody>${d.reminders.map(row).join("")}</tbody></table>`;
    els.count.textContent = (d.total === d.unfiltered_total)
      ? `${d.total} reminder${d.total === 1 ? "" : "s"}`
      : `${d.total} of ${d.unfiltered_total} match`;
  } catch (err) {
    if (mine !== seq) return;
    els.card.innerHTML = `<div class="empty"><h3>Could not load reminders</h3><p>${esc(err.message)}</p></div>`;
    els.count.textContent = "";
  }
}

function clearAll() {
  els.q.value = ""; els.status.value = ""; els.contact.value = ""; els.sort.value = "send_at_asc";
  load();
}
let t = null;
els.q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(load, 250); });
["status", "contact", "sort"].forEach(k => els[k].addEventListener("change", load));
document.getElementById("clear").onclick = clearAll;
window.addEventListener("popstate", () => { readUrl(); load(); });

(async () => { await loadContacts(); readUrl(); load(); })();
</script></body></html>
""".replace("__STYLE__", STYLE).replace("__ESC__", ESC_JS)
