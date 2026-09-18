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
  - There is no "cancel" status. The contract's fourth status is `blocked`,
    which means consent or policy stopped it — not the same as a human
    changing their mind. Cancelling is therefore a delete.

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
    <span class="ico" aria-hidden="true">!</span>
    <div><b>Nothing sends yet.</b> The Reminders Engine is <b>PROJ-395</b>, so a
    scheduled reminder is a record of intent — it will not be delivered until
    that lands. Consent is still enforced at send time (<b>PROJ-441</b>).</div>
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
      <div class="hint">Read in this machine's timezone and stored with an offset.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
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
      <button type="button" class="btn ghost" id="cancel">Cancel</button>
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
  document.getElementById("send_at").value = (d.send_at || "").slice(0, 16);
  await loadContacts(d.contact_id);

  if (d.status && d.status !== "scheduled") {
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
  // Delete is how you cancel: the contract has no 'cancelled' status, and
  // 'blocked' means consent stopped it, which is a different fact.
  if (!confirm("Delete this reminder? There is no 'cancelled' state in the data contract, so cancelling is a delete.")) return;
  const r = await fetch("/api/reminders/" + encodeURIComponent(RID), {method: "DELETE"});
  if (r.ok || r.status === 204) { window.location.href = "/reminders"; }
  else setStatus("Could not delete: HTTP " + r.status);
};

document.getElementById("f").onsubmit = async ev => {
  ev.preventDefault(); clearErrors(); setStatus("");

  const local = {};
  if (!document.getElementById("contact_id").value) local.contact_id = "Choose a contact.";
  if (!msg.value.trim()) local.message = "Enter a message.";
  const when = document.getElementById("send_at").value;
  if (!when) local.send_at = "Enter a valid date and time.";
  else if (new Date(when) <= new Date()) local.send_at = "Pick a time in the future — a past reminder will never send.";
  if (Object.keys(local).length) { showErrors(local); return; }

  const body = {
    contact_id: parseInt(document.getElementById("contact_id").value, 10),
    message: msg.value.trim(),
    send_at: when,
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

loadExisting();
</script></body></html>
""".replace("__STYLE__", STYLE).replace("__ESC__", ESC_JS)


def render(reminder_id: str | None = None) -> str:
    if reminder_id:
        title, subtitle, save = ("Edit reminder", "Change the details and save.", "Save changes")
    else:
        title, subtitle, save = ("New reminder", "Schedule a message to a contact.", "Create reminder")
    return (FORM_HTML.replace("__TITLE__", title).replace("__SUBTITLE__", subtitle)
            .replace("__SAVE__", save).replace("__ID__", reminder_id or ""))
