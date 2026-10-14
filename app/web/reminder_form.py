"""
app.web.reminder_form — create/edit reminder form (PROJ-439).

Rewritten onto the published contract (PROJ-404): `message`, `send_at`, a
required `contact_id`, and no per-reminder channel — the contact's
preferred_channel decides delivery now.

Two things the form surfaces that the earlier version could not, because the
contacts store did not exist:

  - A real contact picker, showing each contact's consent state. Scheduling a
    reminder to someone who has not opted in is allowed (the reminder is a
    plan, not a send), but the form says up front that it will be blocked at
    send time. Discovering that later is worse.
  - Repeat (PROJ-479): none, daily, weekly, or every N days. The bridge adds
    the next occurrence as a new reminder each time one goes out.
  - Pause, resume and cancel (PROJ-479) on an existing reminder. Cancelled is
    its own status, kept in the history; `blocked` still means consent or
    policy stopped it. Rescheduling is editing "Send at" — on a paused
    reminder that moves the time without resuming it.
  - Templates (PROJ-480): pick one to fill the message, and a live preview
    renders its merge fields against the chosen contact and send time — the
    same rendering the bridge does when it sends.

Style and the escape helper are shared with contacts_ui so the pages cannot
drift apart.
"""

from app.web.contacts_ui import ESC_JS, STYLE

FORM_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — Agent Factory</title>__STYLE__</head>
<body><div class="wrap narrow">
  <div class="crumb"><a href="/reminders">&larr; Reminders</a></div>
  <h1>__TITLE__</h1>
  <div class="sub" style="margin-bottom:18px">__SUBTITLE__</div>

  <div class="banner">
    <span class="ico" aria-hidden="true">i</span>
    <div><b>Consent is enforced at send time.</b> Contacts who have not opted in, or
    who have opted out, are blocked automatically and the reminder shows as blocked.</div>
  </div>

  <form id="f" class="card pad" novalidate>
    <input type="hidden" id="rid" value="__ID__">

    <div class="field" id="field-contact_id">
      <label for="contact_id">Contact <span class="req">— required</span></label>
      <select id="contact_id"><option value="">Loading contacts…</option></select>
      <div class="hint" id="contacthint">Every reminder goes to a contact — that is who consent is checked against.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div id="consentwarn"></div>

    <div class="field" id="field-template">
      <label for="template">Start from a template</label>
      <select id="template"><option value="">Loading templates…</option></select>
      <div class="hint">Fills the message below; you can still edit it. <a href="/templates">Manage templates</a>.</div>
    </div>

    <div class="field" id="field-message">
      <label for="message">Message <span class="req">— required</span>
        <span class="counter"><span id="msg-n">0</span>/1600</span></label>
      <textarea id="message" maxlength="1600"
        placeholder="Hi Jane, just a reminder about your appointment tomorrow at 2pm."></textarea>
      <div class="hint">1600 characters is the contract's limit — roughly ten SMS segments.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="field" id="field-send_at">
      <label for="send_at">Send at <span class="req">— required</span></label>
      <input type="datetime-local" id="send_at">
      <div class="hint">Your browser's local time. Sent with its UTC offset, so it means the same moment wherever the server runs.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="field" id="field-recurrence">
      <label for="freq">Repeat</label>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <select id="freq" style="flex:1;min-width:160px">
          <option value="none">Does not repeat</option>
          <option value="daily">Every day</option>
          <option value="weekly">Every week</option>
          <option value="custom">Every N days…</option>
        </select>
        <span id="intervalwrap" style="display:none;gap:6px;align-items:center">
          every <input type="number" id="interval_days" min="1" max="365" value="2"
            style="width:84px" aria-label="Days between reminders"> days
        </span>
      </div>
      <div class="hint">Each repeat goes out at the same local time and keeps its own sent/blocked record.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="card pad" id="preview" style="margin:0 0 14px" hidden>
      <div class="sub" style="margin-bottom:6px"><b>Preview</b> <span id="previewfor"></span></div>
      <div id="previewtext" style="white-space:pre-wrap"></div>
      <div class="sub" id="previewwarn" style="margin-top:6px"></div>
    </div>

    <div class="field" id="field-status">
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>
    <div class="field" id="field-_">
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div id="dispatch"></div>

    <div class="row-actions" style="margin-top:6px">
      <button type="submit" class="btn" id="save">__SAVE__</button>
      <button type="button" class="btn ghost" id="cancel">Back</button>
      <button type="button" class="btn ghost" id="pause" hidden>Pause</button>
      <button type="button" class="btn ghost" id="resume" hidden>Resume</button>
      <button type="button" class="btn ghost" id="cancelrem" hidden>Cancel reminder</button>
      <button type="button" class="btn ghost" id="del" hidden>Delete</button>
      <span id="formstatus" role="status" aria-live="polite"></span>
    </div>
  </form>
</div>
<script>__ESC__
const RID = document.getElementById("rid").value;
let CONTACTS = [];

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
  const first = document.querySelector(".field.bad select, .field.bad textarea, .field.bad input");
  if (first) first.focus();
}
function setStatus(t) { document.getElementById("formstatus").textContent = t; }

const msg = document.getElementById("message");
const msgN = document.getElementById("msg-n");
msg.addEventListener("input", () => { msgN.textContent = msg.value.length; });

const freq = document.getElementById("freq");
const intervalDays = document.getElementById("interval_days");
function syncFreq() {
  // style.display, not .hidden: the span's inline display would override [hidden].
  document.getElementById("intervalwrap").style.display = freq.value === "custom" ? "inline-flex" : "none";
}
freq.addEventListener("change", syncFreq);
function recurrenceBody() {
  if (freq.value === "none") return null;
  // The zone makes "every day at 9am" mean 9am here, through DST changes,
  // even when the server runs in UTC.
  const out = {freq: freq.value, tz: Intl.DateTimeFormat().resolvedOptions().timeZone};
  if (freq.value === "custom") out.interval_days = parseInt(intervalDays.value, 10);
  return out;
}

// ── Templates and live preview (PROJ-480) ───────────────────
let TEMPLATES = [];
async function loadTemplates() {
  const sel = document.getElementById("template");
  try {
    const d = await (await fetch("/api/templates")).json();
    TEMPLATES = d.templates || [];
    sel.innerHTML = TEMPLATES.length
      ? `<option value="">None — write it myself</option>` + TEMPLATES.map(t =>
          `<option value="${esc(String(t.id))}">${esc(t.name)}</option>`).join("")
      : `<option value="">No templates yet</option>`;
  } catch (err) { sel.innerHTML = `<option value="">Could not load templates</option>`; }
}
document.getElementById("template").addEventListener("change", e => {
  const t = TEMPLATES.find(x => String(x.id) === e.target.value);
  if (!t) return;
  if (msg.value.trim() && msg.value !== t.body &&
      !confirm("Replace the current message with this template?")) { e.target.value = ""; return; }
  msg.value = t.body; msgN.textContent = msg.value.length; schedulePreview();
});

let previewTimer = null, previewSeq = 0;
function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(updatePreview, 250); }
async function updatePreview() {
  const box = document.getElementById("preview");
  if (!msg.value.includes("{")) { box.hidden = true; return; }
  const mine = ++previewSeq;
  const when = document.getElementById("send_at").value;
  const cid = document.getElementById("contact_id").value;
  const r = await fetch("/api/templates/preview", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      body: msg.value, contact_id: cid ? parseInt(cid, 10) : null,
      send_at: when ? new Date(when).toISOString() : null,
      tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }),
  }).catch(() => null);
  if (!r || !r.ok || mine !== previewSeq) return;
  const d = await r.json();
  const c = CONTACTS.find(x => String(x.id) === String(cid));
  document.getElementById("previewfor").textContent = c ? "for " + (c.name || c.phone_number) : "(choose a contact)";
  document.getElementById("previewtext").textContent = d.rendered;
  document.getElementById("previewwarn").textContent = d.unknown.length
    ? `Not merge fields, will be sent as written: ${d.unknown.map(u => "{" + u + "}").join(", ")}.` : "";
  box.hidden = false;
}
msg.addEventListener("input", schedulePreview);
document.getElementById("contact_id").addEventListener("change", schedulePreview);
document.getElementById("send_at").addEventListener("change", schedulePreview);

// Pause / resume / cancel (PROJ-479). Each is its own endpoint so the server
// can refuse a transition that does not apply, e.g. resuming a sent reminder.
async function act(action, confirmText) {
  if (confirmText && !confirm(confirmText)) return;
  setStatus("Working…");
  const r = await fetch("/api/reminders/" + encodeURIComponent(RID) + "/" + action, {method: "POST"});
  const d = await r.json().catch(() => ({}));
  if (r.status === 422) { showErrors(d.errors || {}); setStatus("Could not " + action + "."); return; }
  if (!r.ok) { setStatus("Could not " + action + ": " + (d.detail || ("HTTP " + r.status))); return; }
  window.location.reload();
}
document.getElementById("pause").onclick = () => act("pause");
document.getElementById("resume").onclick = () => act("resume");
document.getElementById("cancelrem").onclick = () =>
  act("cancel", "Cancel this reminder? It stays in the list as cancelled and will not send.");

// Say up front that a send will be blocked, rather than after the fact.
function showConsentWarning() {
  const id = document.getElementById("contact_id").value;
  const c = CONTACTS.find(x => String(x.id) === String(id));
  const box = document.getElementById("consentwarn");
  if (!c) { box.innerHTML = ""; return; }
  if (c.consent_state === "opted_in") {
    box.innerHTML = `<div class="banner ok"><span class="ico" aria-hidden="true">\\u2713</span>
      <div>${esc(c.name || c.phone_number)} has opted in.</div></div>`;
  } else {
    box.innerHTML = `<div class="banner bad"><span class="ico" aria-hidden="true">!</span>
      <div><b>This will be blocked at send time.</b> ${esc(c.name || c.phone_number)} is
      ${esc(CONSENT_LABEL[c.consent_state] || c.consent_state).toLowerCase()} — only an explicit
      opt-in permits a send. You can still schedule it.
      <a href="/contacts/${esc(String(c.id))}">Record consent</a>.</div></div>`;
  }
}

async function loadContacts(selected) {
  const sel = document.getElementById("contact_id");
  try {
    const r = await fetch("/api/contacts");
    const d = await r.json();
    CONTACTS = d.contacts || [];
    if (!CONTACTS.length) {
      sel.innerHTML = `<option value="">No contacts yet</option>`;
      document.getElementById("contacthint").innerHTML =
        `You need a contact first — <a href="/contacts/new">add one</a>.`;
      document.getElementById("save").disabled = true;
      return;
    }
    sel.innerHTML = `<option value="">Choose…</option>` + CONTACTS.map(c =>
      `<option value="${esc(String(c.id))}">${esc(c.name || "(no name)")} — ${
        esc(c.phone_number)} · ${esc(CONSENT_LABEL[c.consent_state] || c.consent_state)}</option>`
    ).join("");
    const pre = selected || new URLSearchParams(location.search).get("contact_id");
    if (pre) sel.value = String(pre);
    showConsentWarning();
  } catch (err) {
    sel.innerHTML = `<option value="">Could not load contacts</option>`;
  }
}
document.getElementById("contact_id").addEventListener("change", showConsentWarning);

// datetime-local wants local wall time; the stored value carries an offset
// that may not be this browser's, so convert rather than slice.
function toLocalInput(iso) {
  const dt = new Date(iso || "");
  if (isNaN(dt)) return (iso || "").slice(0, 16);
  const pad = n => String(n).padStart(2, "0");
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

async function loadExisting() {
  if (!RID) { await loadContacts(); return; }
  document.getElementById("del").hidden = false;
  const r = await fetch("/api/reminders/" + encodeURIComponent(RID));
  if (!r.ok) {
    setStatus(r.status === 404 ? "That reminder no longer exists." : "Could not load it.");
    document.getElementById("save").disabled = true;
    await loadContacts();
    return;
  }
  const d = await r.json();
  msg.value = d.message || ""; msgN.textContent = msg.value.length;
  document.getElementById("send_at").value = toLocalInput(d.send_at);
  if (d.recurrence && d.recurrence.freq) {
    freq.value = d.recurrence.freq;
    if (d.recurrence.interval_days) intervalDays.value = d.recurrence.interval_days;
  }
  syncFreq();
  await loadContacts(d.contact_id);

  const editable = d.status === "scheduled" || d.status === "paused";
  document.getElementById("pause").hidden = d.status !== "scheduled";
  document.getElementById("resume").hidden = d.status !== "paused";
  document.getElementById("cancelrem").hidden = !editable;
  document.getElementById("save").disabled = !editable;

  if (d.status === "paused") {
    document.getElementById("dispatch").innerHTML =
      `<div class="banner"><span class="ico" aria-hidden="true">||</span>
        <div><b>Paused.</b> It will not send until you resume it. Changing "Send at"
        reschedules it and leaves it paused.</div></div>`;
  } else if (d.status && d.status !== "scheduled") {
    // The engine owns these. Editing is pointless once it has acted.
    document.getElementById("dispatch").innerHTML =
      `<div class="banner"><span class="ico" aria-hidden="true">!</span>
        <div>This reminder is <b>${esc(d.status)}</b>${
          d.blocked_reason ? ` — ${esc(d.blocked_reason)}` : ""}. Recorded by the engine, not editable here.</div></div>`;
  } else if (d.dispatch && !d.dispatch.allowed) {
    document.getElementById("dispatch").innerHTML =
      `<div class="banner bad"><span class="ico" aria-hidden="true">!</span>
        <div><b>Would be blocked right now.</b> ${esc(d.dispatch.reason || "")}</div></div>`;
  }
}

document.getElementById("cancel").onclick = () => { window.location.href = "/reminders"; };

document.getElementById("del").onclick = async () => {
  // Delete removes the row outright. "Cancel reminder" is the one that keeps
  // a record that someone stopped it.
  if (!confirm("Delete this reminder permanently? To stop it but keep a record, use Cancel reminder.")) return;
  const r = await fetch("/api/reminders/" + encodeURIComponent(RID), {method: "DELETE"});
  if (r.ok || r.status === 204) { window.location.href = "/reminders"; }
  else setStatus("Could not delete: HTTP " + r.status);
};

document.getElementById("f").onsubmit = async ev => {
  ev.preventDefault(); clearErrors(); setStatus("");

  const local = {};
  if (!document.getElementById("contact_id").value) local.contact_id = "Choose a contact.";
  if (freq.value === "custom") {
    const n = parseInt(intervalDays.value, 10);
    if (!(n >= 1 && n <= 365)) local.recurrence = "Repeat every 1 to 365 days.";
  }
  if (!msg.value.trim()) local.message = "Enter a message.";
  const when = document.getElementById("send_at").value;
  if (!when) local.send_at = "Enter a valid date and time.";
  else if (new Date(when) <= new Date()) local.send_at = "Pick a time in the future — a past reminder will never send.";
  if (Object.keys(local).length) { showErrors(local); return; }

  const body = {
    contact_id: parseInt(document.getElementById("contact_id").value, 10),
    message: msg.value.trim(),
    // With an offset: a bare local time would be read in the server's zone,
    // which on a UTC host is hours away from what the user picked.
    send_at: new Date(when).toISOString(),
    recurrence: recurrenceBody(),
  };
  const save = document.getElementById("save");
  save.disabled = true; setStatus("Saving…");
  try {
    const r = await fetch(RID ? "/api/reminders/" + encodeURIComponent(RID) : "/api/reminders", {
      method: RID ? "PATCH" : "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (r.status === 422) { showErrors(d.errors || {}); setStatus("Fix the highlighted fields."); return; }
    if (!r.ok) { setStatus("Could not save: " + (d.detail || ("HTTP " + r.status))); return; }
    setStatus(RID ? "Saved." : "Created.");
    setTimeout(() => { window.location.href = "/reminders"; }, 550);
  } catch (err) { setStatus("Could not save: " + err.message); }
  finally { save.disabled = false; }
};

syncFreq();
loadTemplates();
loadExisting().then(schedulePreview);
</script></body></html>
""".replace("__STYLE__", STYLE).replace("__ESC__", ESC_JS)


def render(reminder_id: str | None = None) -> str:
    if reminder_id:
        title, subtitle, save = ("Edit reminder", "Change the details and save.", "Save changes")
    else:
        title, subtitle, save = ("New reminder", "Schedule a message to a contact.", "Create reminder")
    return (FORM_HTML.replace("__TITLE__", title).replace("__SUBTITLE__", subtitle)
            .replace("__SAVE__", save).replace("__ID__", reminder_id or ""))
