"""
app.web.templates_ui — message template list and editor (PROJ-480).

One page: the templates on the left, an editor on the right. The merge fields
are shown as buttons that insert the placeholder at the cursor, which avoids
the typos the store would otherwise reject ({frist_name}). Style and the
escape helper are shared with contacts_ui, like the reminder pages.
"""

from app.web.contacts_ui import ESC_JS, STYLE

TEMPLATES_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Message templates — Agent Factory</title>__STYLE__
<style>
  .tgrid { display: grid; gap: 16px; grid-template-columns: 280px 1fr; align-items: start; }
  @media (max-width: 760px) { .tgrid { grid-template-columns: 1fr; } }
  .tlist { list-style: none; margin: 0; padding: 6px; }
  .tlist li a { display: block; padding: 9px 10px; border-radius: 6px; text-decoration: none;
    color: var(--text-primary); }
  .tlist li a:hover, .tlist li a[aria-current="true"] { background: var(--surface-2, rgba(127,127,127,.12)); }
  .tlist .sub { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 2px; }
  .chip { font: inherit; font-size: 12px; padding: 3px 8px; border-radius: 999px; cursor: pointer;
    border: 1px solid var(--border); background: transparent; color: var(--text-primary); }
</style></head>
<body><div class="wrap">
  <div class="crumb"><a href="/reminders">&larr; Reminders</a></div>
  <div class="head">
    <div><h1>Message templates</h1><div class="sub" id="count">Loading…</div></div>
    <button type="button" class="btn" id="new">New template</button>
  </div>

  <div class="tgrid">
    <div class="card"><ul class="tlist" id="list"><li class="empty">Loading…</li></ul></div>

    <form id="f" class="card pad" novalidate>
      <input type="hidden" id="tid" value="">
      <div class="field" id="field-name">
        <label for="name">Name <span class="req">— required</span></label>
        <input id="name" maxlength="80" placeholder="Appointment reminder">
        <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
      </div>
      <div class="field" id="field-body">
        <label for="body">Message <span class="req">— required</span>
          <span class="counter"><span id="body-n">0</span>/1600</span></label>
        <textarea id="body" maxlength="1600"
          placeholder="Hi {first_name}, a reminder of your appointment on {date} at {time}. — {org}"></textarea>
        <div class="hint">Insert a merge field — it is filled in for each contact when the reminder sends:</div>
        <div class="chips" id="chips"></div>
        <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
      </div>
      <div class="field" id="field-_">
        <div class="err"><span class="ico" aria-hidden="true">!</span><span class="msg"></span></div>
      </div>
      <div class="row-actions">
        <button type="submit" class="btn" id="save">Save template</button>
        <button type="button" class="btn ghost" id="del" hidden>Delete</button>
        <span id="formstatus" role="status" aria-live="polite"></span>
      </div>
    </form>
  </div>
</div>
<script>__ESC__
let TEMPLATES = [];
const els = {
  list: document.getElementById("list"), count: document.getElementById("count"),
  tid: document.getElementById("tid"), name: document.getElementById("name"),
  body: document.getElementById("body"), bodyN: document.getElementById("body-n"),
  del: document.getElementById("del"),
};
function setStatus(t) { document.getElementById("formstatus").textContent = t; }
function clearErrors() {
  document.querySelectorAll(".field").forEach(f => {
    f.classList.remove("bad"); const m = f.querySelector(".err .msg"); if (m) m.textContent = "";
  });
}
function showErrors(errors) {
  for (const [k, m] of Object.entries(errors || {})) {
    const f = document.getElementById("field-" + k);
    if (f) { f.classList.add("bad"); f.querySelector(".err .msg").textContent = m; }
  }
}
els.body.addEventListener("input", () => { els.bodyN.textContent = els.body.value.length; });

function insertAtCursor(text) {
  const t = els.body, s = t.selectionStart ?? t.value.length, e = t.selectionEnd ?? s;
  t.value = t.value.slice(0, s) + text + t.value.slice(e);
  t.focus(); t.selectionStart = t.selectionEnd = s + text.length;
  els.bodyN.textContent = t.value.length;
}

function edit(t) {
  clearErrors(); setStatus("");
  els.tid.value = t ? t.id : "";
  els.name.value = t ? t.name : "";
  els.body.value = t ? t.body : "";
  els.bodyN.textContent = els.body.value.length;
  els.del.hidden = !t;
  document.querySelectorAll(".tlist a").forEach(a =>
    a.setAttribute("aria-current", String(t && a.dataset.id === String(t.id))));
  history.replaceState(null, "", t ? "?id=" + t.id : location.pathname);
}

function renderList() {
  els.count.textContent = TEMPLATES.length
    ? `${TEMPLATES.length} template${TEMPLATES.length === 1 ? "" : "s"}` : "None yet";
  els.list.innerHTML = TEMPLATES.length ? TEMPLATES.map(t =>
    `<li><a href="#" data-id="${esc(String(t.id))}">${esc(t.name)}
      <span class="sub">${esc(t.body)}</span></a></li>`).join("")
    : `<li class="empty"><h3>No templates yet</h3><p>Write one on the right.</p></li>`;
}
els.list.addEventListener("click", e => {
  const a = e.target.closest("a[data-id]"); if (!a) return;
  e.preventDefault(); edit(TEMPLATES.find(t => String(t.id) === a.dataset.id));
});

async function load(selectId) {
  try {
    const d = await (await fetch("/api/templates")).json();
    TEMPLATES = d.templates || [];
    document.getElementById("chips").innerHTML = (d.merge_fields || []).map(f =>
      `<button type="button" class="chip" title="${esc(f.description)}" data-f="${esc(f.name)}">{${esc(f.name)}}</button>`
    ).join("");
    renderList();
    const want = selectId || new URLSearchParams(location.search).get("id");
    const t = TEMPLATES.find(x => String(x.id) === String(want));
    edit(t || null);
  } catch (err) {
    els.list.innerHTML = `<li class="empty"><h3>Could not load templates</h3><p>${esc(err.message)}</p></li>`;
  }
}
document.getElementById("chips").addEventListener("click", e => {
  const b = e.target.closest("button[data-f]"); if (b) insertAtCursor("{" + b.dataset.f + "}");
});
document.getElementById("new").onclick = () => { edit(null); els.name.focus(); };

els.del.onclick = async () => {
  if (!confirm("Delete this template? Reminders already written from it keep their text.")) return;
  const r = await fetch("/api/templates/" + encodeURIComponent(els.tid.value), {method: "DELETE"});
  if (r.ok || r.status === 204) { setStatus("Deleted."); load(); }
  else setStatus("Could not delete: HTTP " + r.status);
};

document.getElementById("f").onsubmit = async ev => {
  ev.preventDefault(); clearErrors(); setStatus("Saving…");
  const id = els.tid.value;
  const r = await fetch(id ? "/api/templates/" + encodeURIComponent(id) : "/api/templates", {
    method: id ? "PATCH" : "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name: els.name.value, body: els.body.value}),
  });
  const d = await r.json().catch(() => ({}));
  if (r.status === 422) { showErrors(d.errors); setStatus("Fix the highlighted fields."); return; }
  if (!r.ok) { setStatus("Could not save: " + (d.detail || "HTTP " + r.status)); return; }
  await load(d.id); setStatus("Saved.");
};

load();
</script></body></html>
""".replace("__STYLE__", STYLE).replace("__ESC__", ESC_JS)
