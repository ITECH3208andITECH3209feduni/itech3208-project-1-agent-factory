#!/usr/bin/env python3
"""
scripts/build_poster3.py — Poster 3: demo how-to (PROJ-495).

Signs in to a running Agent Factory, takes the six demo-path screenshots,
and renders an A4 poster (PDF + PNG) in the navy/gold style of Poster 2,
with a QR code to the site.

    DEMO_PASSWORD=... python scripts/build_poster3.py https://agent-factory-fvtq.onrender.com

Every screenshot comes from the URL you give, so for the final poster point it
at the live site (the ticket requires screenshots from the deployed build).
Any other URL produces a poster stamped DRAFT. Open <url>/status first: the
free host sleeps and takes about a minute to wake.

The demo password is NOT printed on the poster unless you pass
--show-password: a logged-in visitor can send SMS and email through the
team's accounts, so by default visitors ask at the stand.

Needs: playwright (with Chrome or Edge installed) and segno (`pip install segno`).
"""

from __future__ import annotations

import argparse
import base64
import html
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE_HOST = "agent-factory-fvtq.onrender.com"
DEMO_EMAIL = "poster.demo@example.com"
RECEPTIONIST_NUMBER = "+1 802 444 8729"
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

STEPS = [
    ("login", "Sign in",
     "Open the site and sign in with the demo login. It is a demo clinic with fictional customers."),
    ("contacts", "Check your contacts",
     "Every contact shows their consent. Only people who opted in can be sent a reminder."),
    ("schedule", "Schedule a reminder",
     "Pick a contact and a template, then when and how often. The preview fills in their name and the date."),
    ("consent", "See consent in action",
     "Choose Mei Tanaka, who opted out. The form warns that the reminder will be blocked, and it never sends."),
    ("receptionist", "Call the AI receptionist",
     f"Call {RECEPTIONIST_NUMBER} and ask about opening hours or a booking. Calls, bookings and escalations show here; each call gets a summary and priority."),
    ("dashboard", "Watch the dashboard",
     "Upcoming reminders and everything sent, blocked or failed, in one place."),
]


def _browser_path() -> str | None:
    return next((p for p in BROWSERS if os.path.exists(p)), None)


def take_screenshots(base: str, password: str, out: Path) -> None:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        exe = _browser_path()
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1180, "height": 860}, device_scale_factor=2)
        page.on("dialog", lambda d: d.accept())

        def shot(name: str, top: str, bottom: str | None = None, pad: int = 14,
                 max_h: int = 560) -> None:
            """Screenshot only the part of the page that matters: from the top of
            `top` to the bottom of `bottom` (CSS selectors), so the text stays
            readable at poster size."""
            page.wait_for_timeout(900)   # let fetches and fades settle
            box = page.evaluate(
                """([t, b]) => {
                  const r1 = document.querySelector(t).getBoundingClientRect();
                  const r2 = document.querySelector(b || t).getBoundingClientRect();
                  return {x: Math.min(r1.left, r2.left), y: r1.top,
                          w: Math.max(r1.right, r2.right) - Math.min(r1.left, r2.left),
                          h: r2.bottom - r1.top};
                }""", [top, bottom])
            x, y = max(box["x"] - pad, 0), max(box["y"] - pad, 0)
            w = box["w"] + 2 * pad
            h = min(box["h"] + 2 * pad, max_h)
            page.screenshot(path=str(out / f"{name}.png"), clip={"x": x, "y": y, "width": w, "height": h})

        page.goto(base + "/login", wait_until="networkidle")
        page.fill("#email", DEMO_EMAIL)
        shot("login", ".card")
        page.fill("#password", password)
        page.click("#submit")
        page.wait_for_url(lambda u: "/login" not in u, timeout=60_000)

        page.goto(base + "/crm/contacts", wait_until="networkidle")
        page.wait_for_selector("#card table", timeout=30_000)
        shot("contacts", "#card")

        # Schedule: opted-in contact, template, a time three days out, weekly.
        page.goto(base + "/crm/reminders/new", wait_until="networkidle")
        page.wait_for_selector("#contact_id option:nth-child(2)", state="attached")
        alex = page.locator("#contact_id option", has_text="Alex Rivera").first.get_attribute("value")
        page.select_option("#contact_id", alex)
        page.fill("#send_at", _days_ahead_local(3, "10:30"))
        page.dispatch_event("#send_at", "change")
        if page.locator("#template option", has_text="Appointment reminder").count():
            page.select_option("#template", label="Appointment reminder")
            page.wait_for_selector("#preview:not([hidden])", timeout=15_000)
        page.select_option("#freq", "weekly")
        page.click("h1")   # move focus off the inputs so no field shows a caret
        page.set_viewport_size({"width": 1180, "height": 1400})
        shot("schedule", "#field-send_at", "#preview", max_h=900)
        page.set_viewport_size({"width": 1180, "height": 860})

        # Consent: the opted-out contact.
        page.goto(base + "/crm/reminders/new", wait_until="networkidle")
        page.wait_for_selector("#contact_id option:nth-child(2)", state="attached")
        mei = page.locator("#contact_id option", has_text="Mei Tanaka").first.get_attribute("value")
        page.select_option("#contact_id", mei)
        page.wait_for_selector("#consentwarn .banner.bad")
        shot("consent", "#field-contact_id", "#consentwarn")

        # Receptionist: analytics is re-seeded on every boot; the activity feed
        # only has rows after a real call, and the free host wipes it on sleep.
        page.goto(base + "/", wait_until="networkidle")
        page.evaluate("launchAgent('receptionist')")
        page.evaluate("switchReceptTab('analytics')")
        page.wait_for_timeout(2500)
        shot("receptionist", "#tab-receptionist", pad=0, max_h=520)

        page.goto(base + "/crm/dashboard", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot("dashboard", "main", pad=0, max_h=470)
        browser.close()


def _days_ahead_local(days: int, hhmm: str) -> str:
    from datetime import datetime, timedelta

    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%dT") + hhmm


def _img(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def poster_html(base: str, shots: Path, draft: bool, password: str | None) -> str:
    import segno

    qr_svg = segno.make(base, error="m").svg_inline(scale=6, dark="#1b2a4a", border=2)
    host = base.split("://", 1)[-1]
    login_pw = html.escape(password) if password else "ask us at the stand"
    steps = "\n".join(
        f"""<div class="step"><div class="num">{i}</div>
          <div class="txt"><h3>{html.escape(title)}</h3><p>{html.escape(text)}</p></div>
          <img src="{_img(shots / f'{key}.png')}" alt="{html.escape(title)} screenshot"></div>"""
        for i, (key, title, text) in enumerate(STEPS, 1)
    )
    stamp = ('<div class="draft">DRAFT: screenshots from a local build. '
             'Rebuild from the live site before printing.</div>') if draft else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Poster 3: Try Agent Factory</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif:wght@700&family=Lato:wght@400;700&display=swap" rel="stylesheet">
<style>
  @page {{ size: A4; margin: 0; }}
  :root {{ --navy: #1b2a4a; --gold: #c9a227; --ink: #1f2937; --muted: #5b6475; --line: #d9dee7; --wash: #f4f6fa; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; width: 210mm; height: 297mm; font-family: Lato, "Segoe UI", sans-serif; color: var(--ink);
    background: #fff; position: relative; overflow: hidden; }}
  header {{ background: var(--navy); color: #fff; padding: 8mm 12mm 6mm; }}
  .kicker {{ color: var(--gold); letter-spacing: .32em; font-weight: 700; font-size: 10.5pt; }}
  h1 {{ font-family: "Noto Serif", Georgia, serif; font-size: 24pt; line-height: 1.12; margin: 1.5mm 0 1.5mm; }}
  header p {{ margin: 0; font-size: 11pt; color: #d6dbe6; }}
  .top {{ display: grid; grid-template-columns: 33mm 1fr; gap: 7mm; padding: 5mm 12mm 1mm; align-items: center; }}
  .qr svg {{ width: 33mm; height: 33mm; display: block; }}
  .access h2, .stepsh {{ font-family: "Noto Serif", Georgia, serif; color: var(--navy); font-size: 17pt; margin: 0 0 2mm; }}
  .access dl {{ display: grid; grid-template-columns: 22mm 1fr; gap: 1mm 3mm; margin: 0; font-size: 10.5pt; }}
  .access dt {{ color: var(--muted); }} .access dd {{ margin: 0; font-weight: 700; word-break: break-all; }}
  .stepsh {{ padding: 0 12mm; margin-top: 3mm; }}
  .steps {{ display: grid; grid-template-columns: 1fr 1fr; gap: 3.5mm 5mm; padding: 1mm 12mm 0; }}
  .step {{ border: 1px solid var(--line); border-radius: 3mm; padding: 2.6mm 3mm 3mm; background: #fff; }}
  .step .num {{ float: left; width: 8mm; height: 8mm; border-radius: 50%; background: var(--gold); color: var(--navy);
    font-weight: 700; display: flex; align-items: center; justify-content: center; margin: 0 2.5mm 1mm 0; font-size: 12pt; }}
  .step h3 {{ margin: 0.8mm 0 0.6mm; font-size: 11.5pt; color: var(--navy); }}
  .step p {{ margin: 0 0 1.8mm; font-size: 8.8pt; line-height: 1.3; color: var(--ink); min-height: 11.5mm; }}
  .step img {{ display: block; width: 100%; height: 34mm; object-fit: contain; object-position: center top;
    background: var(--wash); border: 1px solid var(--line); border-radius: 1.5mm; clear: both; }}
  .note {{ margin: 2.5mm 0 0; background: var(--wash); padding: 1.8mm 3mm; font-size: 8.6pt; color: var(--ink); border-radius: 1.5mm; }}
  footer {{ position: absolute; bottom: 6mm; left: 12mm; right: 12mm; font-size: 8.5pt; color: var(--muted);
    display: flex; justify-content: space-between; }}
  .draft {{ position: absolute; top: 4mm; right: 4mm; background: #b42318; color: #fff; font-weight: 700;
    font-size: 9pt; padding: 1.5mm 3mm; border-radius: 1mm; }}
</style></head><body>
{stamp}
<header>
  <div class="kicker">AGENT FACTORY</div>
  <h1>Try it yourself: the demo in six steps</h1>
  <p>Scan the code, sign in, and follow the steps. Everything you see is the live product with fictional customers.</p>
</header>
<section class="top">
  <div class="qr">{qr_svg}</div>
  <div class="access">
    <h2>Open the live demo</h2>
    <dl>
      <dt>Website</dt><dd>{html.escape(host)}</dd>
      <dt>Email</dt><dd>{DEMO_EMAIL}</dd>
      <dt>Password</dt><dd>{login_pw}</dd>
      <dt>Phone</dt><dd>{RECEPTIONIST_NUMBER} (AI receptionist)</dd>
    </dl>
    <p class="note"><b>First visit can take a minute:</b> the free host sleeps when idle.
    All names and numbers are fictional; nothing you schedule reaches a real person.</p>
  </div>
</section>
<h2 class="stepsh">The demo path</h2>
<div class="steps">{steps}</div>
<footer><span>Presenters: open {html.escape(host)}/status a minute before you start, so the site is awake.</span>
<span>Poster 3 of 4 · {date.today():%B %Y}</span></footer>
</body></html>"""


def render(html_text: str, out_pdf: Path, out_png: Path) -> None:
    from playwright.sync_api import sync_playwright

    tmp = out_pdf.with_suffix(".html")
    tmp.write_text(html_text, encoding="utf-8")
    with sync_playwright() as p:
        exe = _browser_path()
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=3)
        page.goto(tmp.resolve().as_uri(), wait_until="networkidle")
        page.pdf(path=str(out_pdf), format="A4", print_background=True,
                 margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        page.screenshot(path=str(out_png), full_page=False)
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="site URL, e.g. https://agent-factory-fvtq.onrender.com")
    ap.add_argument("--out", default=str(ROOT / "docs" / "poster"), help="output folder")
    ap.add_argument("--show-password", action="store_true", help="print DEMO_PASSWORD on the poster")
    ap.add_argument("--skip-shots", action="store_true", help="reuse screenshots already in the out folder")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    password = os.environ.get("DEMO_PASSWORD")
    if not password and not args.skip_shots:
        print("Set DEMO_PASSWORD (the demo login password; on the live site it is the value in Render).")
        return 1
    draft = LIVE_HOST not in base
    out = Path(args.out)
    shots = out / "poster3_screenshots"
    if not args.skip_shots:
        take_screenshots(base, password, shots)
        print(f"screenshots: {shots}")
    html_text = poster_html(base, shots, draft, password if args.show_password else None)
    pdf, png = out / "Poster3_Demo_HowTo.pdf", out / "Poster3_Demo_HowTo.png"
    render(html_text, pdf, png)
    print(f"poster: {pdf}{'  (DRAFT: not the live site)' if draft else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
