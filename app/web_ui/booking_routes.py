# app/web_ui/booking_routes.py
# ──────────────────────────────────────────────────────────────
# The page a patient opens from the confirmation text or email.
#
#   GET  /booking/confirm/{token}  shows the appointment and a Confirm button
#   POST /booking/confirm/{token}  marks it confirmed, then shows it again
#
# Opening the link never confirms anything by itself: phones and mail
# scanners fetch links to build previews, and that must not count as the
# patient saying yes. Only pressing the button (a POST) confirms.
#
# Public (no sign-in), because the patient has no account. The long random
# token in the link is the only key, and only its hash is stored.
# ──────────────────────────────────────────────────────────────

import html
import logging
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from agent import bookings

router = APIRouter()
log = logging.getLogger("agent_factory.bookings")

_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
}

_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title} · {brand}</title>
<style>
  :root {{ --bg:#f4f7fb; --card:#ffffff; --ink:#0f172a; --muted:#475569; --line:#dbe3ee;
          --accent:#0e7490; --ok:#047857; --ok-bg:#d1fae5; --wait:#92400e; --wait-bg:#fef3c7; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#0a0e17; --card:#121826; --ink:#f1f5f9; --muted:#94a3b8; --line:#2b3550;
            --accent:#22d3ee; --ok:#34d399; --ok-bg:#0f2a22; --wait:#fbbf24; --wait-bg:#2e2410; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  main {{ max-width:460px; margin:0 auto; padding:32px 16px; }}
  .brand {{ font-weight:700; color:var(--accent); letter-spacing:.2px; margin-bottom:16px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:22px; }}
  h1 {{ font-size:22px; margin:0 0 6px; }}
  p {{ color:var(--muted); margin:0 0 16px; }}
  dl {{ display:grid; grid-template-columns:auto 1fr; gap:8px 14px; margin:0 0 20px; }}
  dt {{ color:var(--muted); }} dd {{ margin:0; font-weight:600; }}
  .pill {{ display:inline-block; font-size:13px; font-weight:700; padding:3px 10px; border-radius:999px; }}
  .pill.wait {{ color:var(--wait); background:var(--wait-bg); }}
  .pill.ok {{ color:var(--ok); background:var(--ok-bg); }}
  button {{ width:100%; padding:14px; border:0; border-radius:10px; background:var(--accent);
           color:#fff; font-size:17px; font-weight:700; cursor:pointer; }}
  @media (prefers-color-scheme: dark) {{ button {{ color:#0a0e17; }} }}
  button:focus-visible {{ outline:3px solid var(--ink); outline-offset:2px; }}
  .note {{ font-size:14px; margin-top:14px; }}
</style></head>
<body><main>
  <div class="brand">{brand}</div>
  <div class="card">{body}</div>
</main></body></html>"""


def _render(title: str, body: str, status: int = 200) -> HTMLResponse:
    brand = html.escape(bookings.brand_name())
    return HTMLResponse(_PAGE.format(title=html.escape(title), brand=brand, body=body),
                        status_code=status, headers=_HEADERS)


def _details(b: dict) -> str:
    rows = [
        ("Appointment", b["summary"]),
        ("When", bookings.when_text(b["start_local"])),
        ("Name", b["name"]),
    ]
    return "<dl>" + "".join(
        f"<dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd>" for k, v in rows
    ) + "</dl>"


def _is_past(b: dict) -> bool:
    try:
        return datetime.fromisoformat(b["start_local"]) < datetime.now()
    except ValueError:
        return False


@router.get("/booking/confirm/{token}", response_class=HTMLResponse)
async def booking_page(token: str):
    b = bookings.get_by_token(token)
    if not b:
        return _render("Link not valid", "<h1>This link isn't valid</h1><p>It may have been mistyped. "
                       "Please contact the clinic if you need help with your booking.</p>", 404)

    if b["status"] == bookings.CONFIRMED:
        return _render("Appointment confirmed", '<span class="pill ok">Confirmed</span>'
                       "<h1>You're all set</h1><p>Your appointment is confirmed. We'll send you a "
                       "reminder before it.</p>" + _details(b))

    if _is_past(b):
        return _render("Appointment time has passed", '<span class="pill wait">Not confirmed</span>'
                       "<h1>This appointment time has passed</h1><p>Please contact the clinic to "
                       "make a new booking.</p>" + _details(b))

    return _render(
        "Confirm your appointment",
        '<span class="pill wait">Waiting for your confirmation</span>'
        "<h1>Confirm your appointment</h1><p>Please check the details and confirm.</p>"
        + _details(b)
        + f'<form method="post" action="/booking/confirm/{html.escape(token)}">'
          '<button type="submit">Confirm my appointment</button></form>'
          '<p class="note">Need a different time? Call or text the clinic and we\'ll change it.</p>',
    )


@router.post("/booking/confirm/{token}")
async def booking_confirm(token: str):
    b, newly = bookings.confirm_by_token(token)
    if not b:
        return await booking_page(token)
    if newly:
        try:
            bookings.schedule_reminder(b)
        except Exception:  # noqa: BLE001 - confirmation stands even if the reminder fails
            log.exception("reminder after confirmation failed for booking %s", b["id"])
        try:
            from app.web_ui.activity_db import log_activity

            log_activity(
                channel="web", caller=b["name"], intent="booking_confirmed",
                summary=f"{b['name']} confirmed {b['summary']} on {bookings.when_text(b['start_local'])}",
                org_id=b.get("org_id"),
            )
        except Exception:  # noqa: BLE001
            log.exception("could not log booking confirmation activity")
    return RedirectResponse(f"/booking/confirm/{token}", status_code=303, headers=_HEADERS)
