"""
app.web.contacts_ui — contacts list, profile, form, CSV import (PROJ-418, 419, 420).

Four pages sharing one style block. Same conventions as the rest of app/web:
self-contained documents, no build step, no CDN, palette tokens for light and
dark.

Consent state is shown as a coloured dot AND a word everywhere it appears —
it is the field that decides whether anything can be sent, so it must be
readable without relying on colour.
"""

STYLE = """
<style>
  body {
    color-scheme: light;
    --surface-1: #fcfcfb; --page: #f9f9f7;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #898781;
    --hairline: #e1e0d9; --border: rgba(11,11,11,0.10);
    --accent: #2a78d6; --good: #0ca30c; --critical: #d03b3b; --warning: #fab219;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) body {
      color-scheme: dark;
      --surface-1: #1a1a19; --page: #0d0d0d;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
      --hairline: #2c2c2a; --border: rgba(255,255,255,0.10);
      --accent: #3987e5; --critical: #e66767;
    }
  }
  :root[data-theme="dark"] body {
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --hairline: #2c2c2a; --border: rgba(255,255,255,0.10);
    --accent: #3987e5; --critical: #e66767;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--text-primary);
         font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  .wrap { max-width: 1000px; margin: 0 auto; padding: 26px 22px 60px; }
  .narrow { max-width: 620px; }
  .crumb { font-size: 13px; margin-bottom: 14px; }
  a { color: var(--accent); }
  .crumb a { text-decoration: none; }
  .head { display: flex; align-items: baseline; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
  h1 { font-size: 21px; margin: 0; }
  h2 { font-size: 14px; margin: 0 0 8px; }
  .sub { color: var(--text-secondary); font-size: 13px; }
  .btn { padding: 8px 15px; border-radius: 7px; border: 0; font: inherit; font-weight: 600;
         background: var(--accent); color: #fff; text-decoration: none; font-size: 14px; cursor: pointer; }
  .btn.ghost { background: transparent; color: var(--text-secondary);
               border: 1px solid var(--border); font-weight: 500; }
  .btn:disabled { opacity: .55; cursor: default; }
  .row-actions { display: flex; gap: 8px; align-items: center; }

  .card { background: var(--surface-1); border: 1px solid var(--border);
          border-radius: 10px; overflow: hidden; margin-bottom: 16px; }
  .card.pad { padding: 18px 20px; }
  .filters { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end;
             background: var(--surface-1); border: 1px solid var(--border);
             border-radius: 10px; padding: 13px 15px; margin: 16px 0 18px; }
  .fgroup { display: flex; flex-direction: column; gap: 4px; }
  .fgroup.grow { flex: 1 1 220px; }
  .fgroup label, label { display: block; font-size: 11px; text-transform: uppercase;
                         letter-spacing: .06em; color: var(--text-secondary); font-weight: 600; }
  .field { margin-bottom: 16px; }
  .field label { text-transform: none; font-size: 13px; letter-spacing: 0;
                 color: var(--text-primary); margin-bottom: 5px; }
  .req { color: var(--text-secondary); font-weight: 400; }
  .hint { color: var(--text-secondary); font-size: 12px; margin-top: 4px; }
  input, select, textarea { width: 100%; padding: 8px 10px; font: inherit; font-size: 14px;
    color: var(--text-primary); background: var(--page);
    border: 1px solid var(--border); border-radius: 7px; }
  textarea { min-height: 90px; resize: vertical; }
  input:focus, select:focus, textarea:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  .field.bad input, .field.bad select, .field.bad textarea { border-color: var(--critical); }
  .err { display: none; gap: 6px; align-items: baseline; font-size: 12.5px; margin-top: 5px; }
  .field.bad .err { display: flex; }
  .err .ico { color: var(--critical); font-weight: 700; flex: none; }
  .counter { float: right; color: var(--text-secondary); font-size: 12px;
             font-weight: 400; text-transform: none; letter-spacing: 0; }

  table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th, td { text-align: left; padding: 11px 14px; border-bottom: 1px solid var(--hairline); }
  tbody tr:last-child td { border-bottom: 0; }
  th { color: var(--text-secondary); font-weight: 600; font-size: 11px;
       text-transform: uppercase; letter-spacing: .06em; background: var(--page); }
  tbody tr:hover { background: var(--page); }
  td.num, td.phone { font-variant-numeric: tabular-nums; white-space: nowrap; }
  td a { text-decoration: none; font-weight: 500; }
  td.actions { text-align: right; white-space: nowrap; font-size: 13px; }

  /* Consent: dot AND word, never colour alone. */
  .badge { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; white-space: nowrap; }
  .badge .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; background: var(--text-muted); }
  .badge.opted_in  .dot { background: var(--good); }
  .badge.opted_out .dot { background: var(--critical); }
  .badge.pending   .dot { background: var(--accent); }
  .badge.unknown   .dot { background: var(--text-muted); }
  .badge.sent .dot { background: var(--good); }
  .badge.blocked .dot { background: var(--critical); }
  .badge.failed .dot { background: var(--critical); }
  .badge.scheduled .dot { background: var(--accent); }

  .banner { display: flex; gap: 10px; align-items: flex-start;
    background: var(--surface-1); border: 1px solid var(--border);
    border-left: 3px solid var(--warning); border-radius: 8px;
    padding: 10px 13px; margin: 16px 0; font-size: 13px; color: var(--text-secondary); }
  .banner.bad { border-left-color: var(--critical); }
  .banner.ok  { border-left-color: var(--good); }
  .banner .ico { flex: none; font-weight: 700; color: var(--text-primary); }
  .banner b { color: var(--text-primary); font-weight: 600; }

  .empty { padding: 32px 20px; text-align: center; color: var(--text-secondary); }
  .empty h3 { margin: 0 0 6px; font-size: 15px; color: var(--text-primary); }
  .kv { display: grid; grid-template-columns: 160px 1fr; gap: 8px 14px; font-size: 14px; }
  .kv dt { color: var(--text-secondary); font-size: 12.5px; }
  .kv dd { margin: 0; }
  .grid2 { display: grid; gap: 16px; grid-template-columns: 1fr 1fr; }
  @media (max-width: 760px) { .grid2 { grid-template-columns: 1fr; } }
  #formstatus { font-size: 13px; }
  pre.report { background: var(--page); border: 1px solid var(--border); border-radius: 7px;
    padding: 12px; font-size: 12.5px; overflow: auto; max-height: 300px; margin: 0; }
</style>
"""

ESC_JS = """
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const CONSENT_LABEL = {
  unknown: "Never asked", pending: "Invited", opted_in: "Opted in", opted_out: "Opted out",
};
const CHANNEL_LABEL = { sms: "SMS", email: "Email", telegram: "Telegram" };
function consentBadge(state) {
  return `<span class="badge ${esc(state)}"><span class="dot" aria-hidden="true"></span>${
    esc(CONSENT_LABEL[state] || state)}</span>`;
}
"""


# ══════════════════════════════════════════════════════════════
# Contacts list (PROJ-418, 419)
# ══════════════════════════════════════════════════════════════
LIST_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contacts — Agent Factory</title>__STYLE__</head>
<body><div class="wrap">
  <div class="crumb"><a href="/dashboard">&larr; Dashboard</a></div>
  <div class="head">
    <div><h1>Contacts</h1><div class="sub" id="count">Loading…</div></div>
    <div class="row-actions">
      <a class="btn ghost" href="/contacts/import">Import CSV</a>
      <a class="btn" href="/contacts/new">New contact</a>
    </div>
  </div>

  <div class="filters" role="search">
    <div class="fgroup grow"><label for="q">Search</label>
      <input type="search" id="q" placeholder="Name, phone or email…" autocomplete="off"></div>
    <div class="fgroup"><label for="consent">Consent</label>
      <select id="consent">
        <option value="">All</option>
        <option value="opted_in">Opted in</option>
        <option value="pending">Invited</option>
        <option value="unknown">Never asked</option>
        <option value="opted_out">Opted out</option>
      </select></div>
    <button type="button" class="btn ghost" id="clear">Clear</button>
  </div>

  <div class="card" id="card"><div class="empty">Loading…</div></div>
</div>
<script>__ESC__
const els = {q: document.getElementById("q"), consent: document.getElementById("consent"),
             card: document.getElementById("card"), count: document.getElementById("count")};

function params() {
  const p = new URLSearchParams();
  if (els.q.value.trim()) p.set("q", els.q.value.trim());
  if (els.consent.value) p.set("consent_state", els.consent.value);
  return p;
}

let seq = 0;
async function load() {
  const mine = ++seq;
  const qs = params().toString();
  history.replaceState(null, "", qs ? "?" + qs : location.pathname);
  try {
    const r = await fetch("/api/contacts" + (qs ? "?" + qs : ""));
    if (mine !== seq) return;
    if (r.status === 422) {
      const d = await r.json();
      els.card.innerHTML = `<div class="empty"><h3>Invalid filter</h3><p>${
        esc(Object.values(d.errors||{}).join(" "))}</p></div>`;
      return;
    }
    if (!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();
    if (mine !== seq) return;

    if (!d.contacts.length) {
      const filtered = els.q.value.trim() || els.consent.value;
      els.card.innerHTML = filtered
        ? `<div class="empty"><h3>Nothing matches these filters</h3>
             <p><a href="#" id="ci">Clear filters</a></p></div>`
        : `<div class="empty"><h3>No contacts yet</h3>
             <p>Add one, or <a href="/contacts/import">import a CSV</a>.</p>
             <a class="btn" href="/contacts/new">New contact</a></div>`;
      const ci = document.getElementById("ci");
      if (ci) ci.onclick = e => { e.preventDefault(); clearAll(); };
      els.count.textContent = filtered ? "0 match" : "None yet";
      return;
    }

    els.card.innerHTML = `<table><thead><tr>
        <th>Name</th><th>Phone</th><th>Channel</th><th>Consent</th><th>Quiet hours</th><th></th>
      </tr></thead><tbody>` + d.contacts.map(c => `
        <tr>
          <td><a href="/contacts/${c.id}">${esc(c.name || "(no name)")}</a></td>
          <td class="phone">${esc(c.phone_number)}</td>
          <td>${esc(CHANNEL_LABEL[c.preferred_channel] || c.preferred_channel || "SMS")}</td>
          <td>${consentBadge(c.consent_state)}</td>
          <td class="num">${c.quiet_hours_start
              ? esc(c.quiet_hours_start) + "–" + esc(c.quiet_hours_end) : "—"}</td>
          <td class="actions"><a href="/contacts/${c.id}">Open</a></td>
        </tr>`).join("") + `</tbody></table>`;
    els.count.textContent = `${d.count} contact${d.count === 1 ? "" : "s"}`;
  } catch (err) {
    if (mine !== seq) return;
    els.card.innerHTML = `<div class="empty"><h3>Could not load contacts</h3><p>${esc(err.message)}</p></div>`;
  }
}

function clearAll() { els.q.value = ""; els.consent.value = ""; load(); }
let t = null;
els.q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(load, 250); });
els.consent.addEventListener("change", load);
document.getElementById("clear").onclick = clearAll;

const p0 = new URLSearchParams(location.search);
els.q.value = p0.get("q") || "";
els.consent.value = p0.get("consent_state") || "";
load();
</script></body></html>
""".replace("__STYLE__", STYLE).replace("__ESC__", ESC_JS)


# ══════════════════════════════════════════════════════════════
# Contact form (PROJ-418, 440)
# ══════════════════════════════════════════════════════════════
FORM_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — Agent Factory</title>__STYLE__</head>
<body><div class="wrap narrow">
  <div class="crumb"><a href="/contacts">&larr; Contacts</a></div>
  <h1>__TITLE__</h1>
  <div class="sub" style="margin-bottom:18px">Phone number is the identifier — it is stored in E.164 form, so 0412 345 678 and +61412345678 are the same person.</div>

  <form id="f" class="card pad" novalidate>
    <input type="hidden" id="cid" value="__ID__">

    <div class="field" id="field-phone_number">
      <label for="phone_number">Phone number <span class="req">— required</span></label>
      <input type="text" id="phone_number" placeholder="0412 345 678" autocomplete="off">
      <div class="hint">Australian numbers starting 0 become +61 automatically.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="field" id="field-name">
      <label for="name">Name <span class="req">— optional</span>
        <span class="counter"><span id="name-n">0</span>/120</span></label>
      <input type="text" id="name" maxlength="120" autocomplete="off">
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="field" id="field-email">
      <label for="email">Email <span class="req">— optional</span></label>
      <input type="text" id="email" autocomplete="off" placeholder="name@example.com">
      <div class="hint">Required before the email channel can be selected.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="grid2">
      <div class="field" id="field-preferred_channel">
        <label for="preferred_channel">Preferred channel</label>
        <select id="preferred_channel">
          <option value="sms">SMS</option>
          <option value="email">Email</option>
          <option value="telegram">Telegram</option>
        </select>
        <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
      </div>
      <div class="field" id="field-consent_state">
        <label for="consent_state">Consent</label>
        <select id="consent_state">
          <option value="unknown">Never asked</option>
          <option value="pending">Invited</option>
          <option value="opted_in">Opted in</option>
          <option value="opted_out">Opted out</option>
        </select>
        <div class="hint">Only an explicit opt-in permits a send.</div>
        <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
      </div>
    </div>

    <div class="grid2">
      <div class="field" id="field-quiet_hours_start">
        <label for="quiet_hours_start">Quiet hours from</label>
        <input type="text" id="quiet_hours_start" placeholder="21:00" autocomplete="off">
        <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
      </div>
      <div class="field" id="field-quiet_hours_end">
        <label for="quiet_hours_end">until</label>
        <input type="text" id="quiet_hours_end" placeholder="07:00" autocomplete="off">
        <div class="hint">Windows may cross midnight.</div>
        <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
      </div>
    </div>

    <div class="field" id="field-_">
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="row-actions" style="margin-top:6px">
      <button type="submit" class="btn" id="save">__SAVE__</button>
      <button type="button" class="btn ghost" id="cancel">Cancel</button>
      <span id="formstatus" role="status" aria-live="polite"></span>
    </div>
  </form>
</div>
<script>__ESC__
const CID = document.getElementById("cid").value;

function clearErrors() {
  document.querySelectorAll(".field").forEach(f => {
    f.classList.remove("bad");
    const m = f.querySelector(".err .msg"); if (m) m.textContent = "";
  });
}
function showErrors(errors) {
  for (const [k, msg] of Object.entries(errors || {})) {
    const f = document.getElementById("field-" + k);
    if (f) { f.classList.add("bad"); f.querySelector(".err .msg").textContent = msg; }
  }
  const first = document.querySelector(".field.bad input, .field.bad select");
  if (first) first.focus();
}
function setStatus(t) { document.getElementById("formstatus").textContent = t; }

const nameIn = document.getElementById("name");
const nameN = document.getElementById("name-n");
nameIn.addEventListener("input", () => { nameN.textContent = nameIn.value.length; });

async function loadExisting() {
  if (!CID) return;
  const r = await fetch("/api/contacts/" + encodeURIComponent(CID));
  if (!r.ok) { setStatus(r.status === 404 ? "That contact no longer exists." : "Could not load it.");
               document.getElementById("save").disabled = true; return; }
  const d = await r.json();
  document.getElementById("phone_number").value = d.phone_number || "";
  nameIn.value = d.name || ""; nameN.textContent = (d.name || "").length;
  document.getElementById("email").value = d.email || "";
  document.getElementById("preferred_channel").value = d.preferred_channel || "sms";
  document.getElementById("consent_state").value = d.consent_state || "unknown";
  document.getElementById("quiet_hours_start").value = d.quiet_hours_start || "";
  document.getElementById("quiet_hours_end").value = d.quiet_hours_end || "";
}

document.getElementById("cancel").onclick = () => {
  window.location.href = CID ? "/contacts/" + encodeURIComponent(CID) : "/contacts";
};

document.getElementById("f").onsubmit = async ev => {
  ev.preventDefault(); clearErrors(); setStatus("");
  const body = {
    phone_number: document.getElementById("phone_number").value.trim(),
    name: nameIn.value.trim(),
    email: document.getElementById("email").value.trim(),
    preferred_channel: document.getElementById("preferred_channel").value,
    consent_state: document.getElementById("consent_state").value,
    quiet_hours_start: document.getElementById("quiet_hours_start").value.trim(),
    quiet_hours_end: document.getElementById("quiet_hours_end").value.trim(),
  };
  const save = document.getElementById("save");
  save.disabled = true; setStatus("Saving…");
  try {
    const r = await fetch(CID ? "/api/contacts/" + encodeURIComponent(CID) : "/api/contacts", {
      method: CID ? "PATCH" : "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (r.status === 422) { showErrors(d.errors || {}); setStatus("Fix the highlighted fields."); return; }
    if (!r.ok) { setStatus("Could not save: " + (d.detail || ("HTTP " + r.status))); return; }
    setStatus("Saved.");
    setTimeout(() => { window.location.href = "/contacts/" + encodeURIComponent(d.id || CID); }, 500);
  } catch (err) { setStatus("Could not save: " + err.message); }
  finally { save.disabled = false; }
};
loadExisting();
</script></body></html>
""".replace("__STYLE__", STYLE).replace("__ESC__", ESC_JS)


def render_form(contact_id: str | None = None) -> str:
    if contact_id:
        return (FORM_HTML.replace("__TITLE__", "Edit contact")
                .replace("__SAVE__", "Save changes").replace("__ID__", str(contact_id)))
    return (FORM_HTML.replace("__TITLE__", "New contact")
            .replace("__SAVE__", "Create contact").replace("__ID__", ""))


# ══════════════════════════════════════════════════════════════
# Contact profile (PROJ-419, 440, 441)
# ══════════════════════════════════════════════════════════════
PROFILE_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contact — Agent Factory</title>__STYLE__</head>
<body><div class="wrap">
  <div class="crumb"><a href="/contacts">&larr; Contacts</a></div>
  <div class="head">
    <div><h1 id="cname">Loading…</h1><div class="sub" id="cphone"></div></div>
    <div class="row-actions">
      <a class="btn ghost" id="editlink" href="#">Edit</a>
      <a class="btn" id="remindlink" href="#">New reminder</a>
    </div>
  </div>

  <div id="senddecision"></div>

  <div class="grid2">
    <div class="card pad">
      <h2>Details</h2>
      <dl class="kv" id="details"></dl>
    </div>
    <div class="card pad">
      <h2>Consent</h2>
      <div id="consentnow" style="margin-bottom:12px"></div>
      <div class="row-actions" style="margin-bottom:14px">
        <button class="btn ghost" id="optin">Record opt-in</button>
        <button class="btn ghost" id="optout">Record opt-out</button>
      </div>
      <div class="sub" id="consenterr" style="color:var(--critical)"></div>
      <h2 style="margin-top:14px">Audit trail</h2>
      <div id="consenthistory" class="sub">Loading…</div>
    </div>
  </div>

  <div class="card">
    <div class="pad" style="padding-bottom:0"><h2>Reminders for this contact</h2></div>
    <div id="reminders"><div class="empty">Loading…</div></div>
  </div>
</div>
<script>__ESC__
const CID = "__ID__";
const STATUS_LABEL = {scheduled:"Scheduled", sent:"Sent", blocked:"Blocked", failed:"Failed"};

function fmt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? esc(iso) : d.toLocaleString(undefined,
    {year:"numeric", month:"short", day:"2-digit", hour:"2-digit", minute:"2-digit"});
}

async function load() {
  const r = await fetch("/api/contacts/" + encodeURIComponent(CID));
  if (!r.ok) {
    document.getElementById("cname").textContent = r.status === 404 ? "Contact not found" : "Could not load";
    return;
  }
  const c = await r.json();

  document.getElementById("cname").textContent = c.name || "(no name)";
  document.getElementById("cphone").textContent = c.phone_number;
  document.getElementById("editlink").href = "/contacts/" + c.id + "/edit";
  document.getElementById("remindlink").href = "/reminders/new?contact_id=" + c.id;

  document.getElementById("details").innerHTML = `
    <dt>Phone</dt><dd>${esc(c.phone_number)}</dd>
    <dt>Email</dt><dd>${esc(c.email || "—")}</dd>
    <dt>Preferred channel</dt><dd>${esc(CHANNEL_LABEL[c.preferred_channel] || c.preferred_channel || "SMS")}</dd>
    <dt>Quiet hours</dt><dd>${c.quiet_hours_start
        ? esc(c.quiet_hours_start) + " – " + esc(c.quiet_hours_end) : "None set"}</dd>
    <dt>Added</dt><dd>${fmt(c.created_at)}</dd>
    <dt>Contact id</dt><dd>#${esc(String(c.id))}</dd>`;

  document.getElementById("consentnow").innerHTML = consentBadge(c.consent_state);

  // Whether a send is currently permitted, and why not. Shown here so it is
  // known before scheduling rather than after a block.
  const sd = c.send_decision || {};
  document.getElementById("senddecision").innerHTML =
    `<div class="banner ${sd.allowed ? "ok" : "bad"}">
       <span class="ico" aria-hidden="true">${sd.allowed ? "\\u2713" : "!"}</span>
       <div><b>${sd.allowed ? "Sending allowed." : "Sending blocked."}</b> ${esc(sd.reason || "")}</div>
     </div>`;

  const hist = c.consent_history || [];
  document.getElementById("consenthistory").innerHTML = hist.length
    ? hist.map(h => `<div style="padding:5px 0;border-bottom:1px solid var(--hairline)">
        ${esc(CONSENT_LABEL[h.old_state] || h.old_state || "—")} &rarr;
        <b>${esc(CONSENT_LABEL[h.new_state] || h.new_state)}</b>
        <span class="sub"> · ${esc(h.source)} · ${fmt(h.occurred_at)}</span>
        ${h.detail ? `<div class="sub">${esc(h.detail)}</div>` : ""}</div>`).join("")
    : "No consent events recorded.";

  const rr = await fetch("/api/reminders?contact_id=" + encodeURIComponent(CID) + "&sort=send_at_desc");
  const rd = rr.ok ? await rr.json() : {reminders: []};
  document.getElementById("reminders").innerHTML = rd.reminders.length
    ? `<table><thead><tr><th>Message</th><th>Send at</th><th>Status</th></tr></thead><tbody>` +
      rd.reminders.map(x => `<tr>
        <td><a href="/reminders/${x.id}/edit">${esc((x.message || "").slice(0, 70))}</a></td>
        <td class="num">${fmt(x.send_at)}</td>
        <td><span class="badge ${esc(x.status)}"><span class="dot" aria-hidden="true"></span>${
          esc(STATUS_LABEL[x.status] || x.status)}</span>${
          x.blocked_reason ? `<div class="sub">${esc(x.blocked_reason)}</div>` : ""}</td>
      </tr>`).join("") + `</tbody></table>`
    : `<div class="empty">No reminders for this contact.
         <a href="/reminders/new?contact_id=${esc(CID)}">Create one</a>.</div>`;
}

async function setConsent(state) {
  document.getElementById("consenterr").textContent = "";
  const r = await fetch("/api/contacts/" + encodeURIComponent(CID) + "/consent", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({state, source: "manual", detail: "recorded from contact profile"}),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    document.getElementById("consenterr").textContent =
      Object.values(d.errors || {}).join(" ") || d.detail || ("HTTP " + r.status);
    return;
  }
  load();
}
document.getElementById("optin").onclick = () => setConsent("opted_in");
document.getElementById("optout").onclick = () => setConsent("opted_out");
load();
</script></body></html>
""".replace("__STYLE__", STYLE).replace("__ESC__", ESC_JS)


def render_profile(contact_id: int) -> str:
    return PROFILE_HTML.replace("__ID__", str(int(contact_id)))


# ══════════════════════════════════════════════════════════════
# CSV import (PROJ-420)
# ══════════════════════════════════════════════════════════════
IMPORT_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Import contacts — Agent Factory</title>__STYLE__</head>
<body><div class="wrap narrow">
  <div class="crumb"><a href="/contacts">&larr; Contacts</a></div>
  <h1>Import contacts</h1>
  <div class="sub" style="margin-bottom:18px">
    CSV with a <code>phone_number</code> column. Optional:
    <code>name</code>, <code>email</code>, <code>preferred_channel</code>,
    <code>quiet_hours_start</code>, <code>quiet_hours_end</code>, <code>consent_state</code>.
    <a href="/api/contacts-template.csv">Download a template</a>.
  </div>

  <div class="banner">
    <span class="ico" aria-hidden="true">!</span>
    <div><b>Imported contacts are not opted in.</b> Unless the file says
    otherwise they are recorded as <i>never asked</i>, and nothing can be sent
    to them until consent is captured. Importing a list is not consent.</div>
  </div>

  <div class="card pad">
    <div class="field">
      <label for="file">CSV file</label>
      <input type="file" id="file" accept=".csv,text/csv">
    </div>
    <div class="row-actions">
      <button class="btn ghost" id="dry">Check without importing</button>
      <button class="btn" id="go">Import</button>
      <span id="formstatus" role="status" aria-live="polite"></span>
    </div>
  </div>

  <div id="result"></div>
</div>
<script>__ESC__
function setStatus(t) { document.getElementById("formstatus").textContent = t; }

function renderReport(d) {
  const lines = [];
  if (d.unknown_columns && d.unknown_columns.length)
    lines.push(`Ignored unknown column(s): ${d.unknown_columns.join(", ")}`);
  for (const f of d.failed) lines.push(`Line ${f.line}: FAILED — ${f.error}`);
  for (const s of d.skipped) lines.push(`Line ${s.line}: skipped — ${s.reason}`);
  for (const c of d.created) lines.push(`Line ${c.line}: ${d.dry_run ? "would import" : "imported"} ${c.phone_number}`);

  const kind = d.failed_count ? "bad" : "ok";
  document.getElementById("result").innerHTML = `
    <div class="banner ${kind}">
      <span class="ico" aria-hidden="true">${d.failed_count ? "!" : "\\u2713"}</span>
      <div><b>${d.dry_run ? "Dry run — nothing was written." : "Import complete."}</b>
        ${d.created_count} ${d.dry_run ? "would be created" : "created"},
        ${d.skipped_count} skipped, ${d.failed_count} failed.</div>
    </div>
    <div class="card pad"><h2>Per-row report</h2>
      <pre class="report">${esc(lines.join("\\n")) || "Nothing to report."}</pre>
      ${!d.dry_run && d.created_count ? `<div style="margin-top:12px"><a class="btn" href="/contacts">View contacts</a></div>` : ""}
    </div>`;
}

async function upload(dryRun) {
  const f = document.getElementById("file").files[0];
  if (!f) { setStatus("Choose a file first."); return; }
  setStatus(dryRun ? "Checking…" : "Importing…");
  document.getElementById("go").disabled = true;
  document.getElementById("dry").disabled = true;
  try {
    const r = await fetch("/api/contacts/import" + (dryRun ? "?dry_run=true" : ""), {
      method: "POST", headers: {"Content-Type": "text/csv"}, body: await f.arrayBuffer(),
    });
    const d = await r.json().catch(() => ({}));
    if (r.status === 422) {
      setStatus("");
      document.getElementById("result").innerHTML =
        `<div class="banner bad"><span class="ico" aria-hidden="true">!</span><div><b>Could not read that file.</b> ${
          esc(Object.values(d.errors || {}).join(" "))}</div></div>`;
      return;
    }
    if (!r.ok) { setStatus("Failed: HTTP " + r.status); return; }
    setStatus("");
    renderReport(d);
  } catch (err) { setStatus("Failed: " + err.message); }
  finally {
    document.getElementById("go").disabled = false;
    document.getElementById("dry").disabled = false;
  }
}
document.getElementById("dry").onclick = () => upload(true);
document.getElementById("go").onclick = () => upload(false);
</script></body></html>
""".replace("__STYLE__", STYLE).replace("__ESC__", ESC_JS)
