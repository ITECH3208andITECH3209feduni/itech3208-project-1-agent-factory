"""
app.web.reminder_form — create/edit reminder form (PROJ-439).

Served at /reminders/new and /reminders/{id}/edit. Same conventions as the
dashboard: one self-contained document, no build step, no CDN, palette tokens
declared for light and dark.

The form posts to /api/reminders and renders the server's per-field errors
beside the inputs. Client-side checks exist to catch mistakes early, but the
server is the authority — app.web.reminders.validate is the single source of
truth and is what survives when PROJ-422 replaces the store.
"""

FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — Agent Factory</title>
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
    --critical:       #d03b3b;
    --warning:        #fab219;
    --good:           #0ca30c;
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
      --critical:       #e66767;
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
  body {
    margin: 0; background: var(--page); color: var(--text-primary);
    font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  .wrap { max-width: 620px; margin: 0 auto; padding: 28px 22px 60px; }

  .crumb { font-size: 13px; margin-bottom: 14px; }
  .crumb a { color: var(--accent); text-decoration: none; }
  .crumb a:hover { text-decoration: underline; }
  h1 { font-size: 21px; margin: 0 0 4px; }
  .sub { color: var(--text-secondary); font-size: 13px; margin-bottom: 20px; }

  .banner {
    display: flex; gap: 10px; align-items: flex-start;
    background: var(--surface-1); border: 1px solid var(--border);
    border-left: 3px solid var(--warning);
    border-radius: 8px; padding: 11px 14px; margin-bottom: 20px;
    font-size: 13px; color: var(--text-secondary);
  }
  .banner .ico { flex: none; font-weight: 700; color: var(--text-primary); }
  .banner b { color: var(--text-primary); font-weight: 600; }

  form {
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 10px; padding: 20px 22px;
  }
  .field { margin-bottom: 17px; }
  label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 5px; }
  .req { color: var(--text-secondary); font-weight: 400; }
  .hint { color: var(--text-secondary); font-size: 12px; margin-top: 4px; }

  input[type=text], input[type=datetime-local], select, textarea {
    width: 100%; padding: 9px 11px; font: inherit;
    color: var(--text-primary); background: var(--page);
    border: 1px solid var(--border); border-radius: 7px;
  }
  textarea { min-height: 88px; resize: vertical; }
  input:focus, select:focus, textarea:focus {
    outline: 2px solid var(--accent); outline-offset: -1px;
  }
  .field.bad input, .field.bad select, .field.bad textarea { border-color: var(--critical); }

  /* Errors carry an icon and text, never colour alone. */
  .err {
    display: none; gap: 6px; align-items: baseline;
    color: var(--text-primary); font-size: 12.5px; margin-top: 5px;
  }
  .field.bad .err { display: flex; }
  .err .ico { color: var(--critical); font-weight: 700; flex: none; }

  .counter { float: right; color: var(--text-secondary); font-size: 12px; font-weight: 400; }

  .actions { display: flex; gap: 10px; align-items: center; margin-top: 22px; }
  button {
    padding: 10px 20px; border-radius: 7px; border: 0; font: inherit;
    font-weight: 600; cursor: pointer; background: var(--accent); color: #fff;
  }
  button.ghost {
    background: transparent; color: var(--text-secondary);
    border: 1px solid var(--border); font-weight: 500;
  }
  button:disabled { opacity: .55; cursor: default; }
  #formstatus { font-size: 13px; color: var(--text-primary); }
</style>
</head>
<body>
<div class="wrap">
  <div class="crumb"><a href="/dashboard">&larr; Dashboard</a></div>
  <h1 id="heading">__TITLE__</h1>
  <div class="sub" id="subtitle">__SUBTITLE__</div>

  <div class="banner">
    <span class="ico" aria-hidden="true">!</span>
    <div>
      <b>Provisional backend.</b> Reminders are saved to a local JSON file, not
      the real store — that is <b>PROJ-422</b>, coded against the data contract
      <b>PROJ-404</b>, neither of which has landed. The shape used here is
      written down in <code>docs/contracts/reminder.provisional.schema.json</code>.
      Nothing sends: the Reminders Engine is <b>PROJ-395</b>.
    </div>
  </div>

  <form id="f" novalidate>
    <input type="hidden" id="rid" value="__ID__">

    <div class="field" id="field-title">
      <label for="title">Title <span class="req">— required</span>
        <span class="counter"><span id="title-n">0</span>/200</span></label>
      <input type="text" id="title" maxlength="200" autocomplete="off"
             placeholder="Follow up with Acme about renewal">
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="field" id="field-due_at">
      <label for="due_at">Due <span class="req">— required</span></label>
      <input type="datetime-local" id="due_at">
      <div class="hint" id="due-hint">Interpreted in this machine's timezone and stored with an offset.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="field" id="field-channel">
      <label for="channel">Channel <span class="req">— required</span></label>
      <select id="channel">
        <option value="">Choose…</option>
        <option value="telegram">Telegram</option>
        <option value="email">Email</option>
        <option value="sms">SMS</option>
      </select>
      <div class="hint">Per-contact preference and quiet hours are PROJ-400 and are not applied yet.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="field" id="field-status">
      <label for="status">Status</label>
      <select id="status">
        <option value="scheduled">Scheduled</option>
        <option value="cancelled">Cancelled</option>
      </select>
      <div class="hint">Sent and failed are set by the engine, not here.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="field" id="field-contact_id">
      <label for="contact_id">Contact <span class="req">— optional</span></label>
      <input type="text" id="contact_id" autocomplete="off" placeholder="Contact ID">
      <div class="hint">A free-text ID for now — the contacts store is PROJ-417, so this is not checked.</div>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="field" id="field-notes">
      <label for="notes">Notes <span class="req">— optional</span>
        <span class="counter"><span id="notes-n">0</span>/2000</span></label>
      <textarea id="notes" maxlength="2000"></textarea>
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="field" id="field-_">
      <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
    </div>

    <div class="actions">
      <button type="submit" id="save">__SAVE_LABEL__</button>
      <button type="button" class="ghost" id="cancel">Cancel</button>
      <span id="formstatus" role="status" aria-live="polite"></span>
    </div>
  </form>
</div>

<script>
const RID = document.getElementById("rid").value;
const FIELDS = ["title", "due_at", "channel", "status", "contact_id", "notes"];

function clearErrors() {
  document.querySelectorAll(".field").forEach(f => {
    f.classList.remove("bad");
    const m = f.querySelector(".err .msg");
    if (m) m.textContent = "";
  });
}

function showErrors(errors) {
  // Keyed by field name, so each message lands beside the input it concerns.
  for (const [key, msg] of Object.entries(errors || {})) {
    const f = document.getElementById("field-" + key);
    if (f) {
      f.classList.add("bad");
      f.querySelector(".err .msg").textContent = msg;
    }
  }
  const first = document.querySelector(".field.bad input, .field.bad select, .field.bad textarea");
  if (first) first.focus();
}

function setStatus(text, kind) {
  const el = document.getElementById("formstatus");
  el.textContent = text;
  el.className = kind || "";
}

// Live counters — cheap, and stops people discovering the limit on submit.
for (const [id, out] of [["title", "title-n"], ["notes", "notes-n"]]) {
  const input = document.getElementById(id);
  const label = document.getElementById(out);
  const sync = () => { label.textContent = input.value.length; };
  input.addEventListener("input", sync);
  sync();
}

// Client-side checks mirror the server's, but the server is the authority —
// these only save a round trip on obvious mistakes.
function localErrors() {
  const errs = {};
  const title = document.getElementById("title").value.trim();
  if (!title) errs.title = "Enter a title.";

  const due = document.getElementById("due_at").value;
  if (!due) {
    errs.due_at = "Enter a valid date and time.";
  } else if (document.getElementById("status").value === "scheduled"
             && new Date(due) <= new Date()) {
    errs.due_at = "Pick a time in the future — a past reminder will never send.";
  }

  if (!document.getElementById("channel").value) errs.channel = "Choose a channel.";
  return errs;
}

async function loadExisting() {
  if (!RID) return;
  try {
    const r = await fetch("/api/reminders/" + encodeURIComponent(RID));
    if (!r.ok) {
      setStatus(r.status === 404 ? "That reminder no longer exists." : "Could not load it.", "bad");
      document.getElementById("save").disabled = true;
      return;
    }
    const d = await r.json();
    document.getElementById("title").value = d.title || "";
    // datetime-local wants no offset, so trim it off for display while the
    // stored value keeps its offset.
    document.getElementById("due_at").value = (d.due_at || "").slice(0, 16);
    document.getElementById("channel").value = d.channel || "";
    document.getElementById("contact_id").value = d.contact_id || "";
    document.getElementById("notes").value = d.notes || "";

    const sel = document.getElementById("status");
    // A reminder the engine already marked sent/failed must remain visible in
    // the dropdown without becoming client-settable.
    if (d.status && !["scheduled", "cancelled"].includes(d.status)) {
      const opt = document.createElement("option");
      opt.value = d.status;
      opt.textContent = d.status + " (set by the engine)";
      opt.disabled = true;
      sel.appendChild(opt);
    }
    sel.value = d.status || "scheduled";

    document.getElementById("title-n").textContent = (d.title || "").length;
    document.getElementById("notes-n").textContent = (d.notes || "").length;
  } catch (err) {
    setStatus("Could not load it: " + err.message, "bad");
  }
}

document.getElementById("cancel").onclick = () => { window.location.href = "/dashboard"; };

document.getElementById("f").onsubmit = async ev => {
  ev.preventDefault();
  clearErrors();
  setStatus("");

  const local = localErrors();
  if (Object.keys(local).length) { showErrors(local); return; }

  const body = {
    title:      document.getElementById("title").value.trim(),
    due_at:     document.getElementById("due_at").value,
    channel:    document.getElementById("channel").value,
    status:     document.getElementById("status").value,
    contact_id: document.getElementById("contact_id").value.trim() || null,
    notes:      document.getElementById("notes").value,
  };

  const save = document.getElementById("save");
  save.disabled = true;
  setStatus("Saving…");

  try {
    const r = await fetch(RID ? "/api/reminders/" + encodeURIComponent(RID) : "/api/reminders", {
      method: RID ? "PATCH" : "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));

    if (r.status === 422) {
      showErrors(d.errors || {});
      setStatus("Fix the highlighted fields.", "bad");
      return;
    }
    if (!r.ok) {
      setStatus("Could not save: " + (d.detail || ("HTTP " + r.status)), "bad");
      return;
    }

    setStatus(RID ? "Saved." : "Created.", "ok");
    // Back to the dashboard so the counter reflects the change.
    setTimeout(() => { window.location.href = "/dashboard"; }, 650);
  } catch (err) {
    setStatus("Could not save: " + err.message, "bad");
  } finally {
    save.disabled = false;
  }
};

loadExisting();
</script>
</body>
</html>
"""


def render(reminder_id: str | None = None) -> str:
    """Render the form for create (no id) or edit (with id)."""
    if reminder_id:
        title, subtitle, save = (
            "Edit reminder",
            "Change the details and save.",
            "Save changes",
        )
    else:
        title, subtitle, save = (
            "New reminder",
            "Schedule a reminder for a contact.",
            "Create reminder",
        )

    return (
        FORM_HTML
        .replace("__TITLE__", title)
        .replace("__SUBTITLE__", subtitle)
        .replace("__SAVE_LABEL__", save)
        .replace("__ID__", reminder_id or "")
    )
