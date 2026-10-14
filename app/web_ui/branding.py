"""Optional clinic branding for the hosted demo.

By default the app is "Agent Factory". Setting BRAND_NAME renames it on the
sign-in pages and the dashboard, and BRAND_MODE=clinic also switches to the
dental-clinic look: the research agents are hidden, the receptionist opens
straight away, and the accent colour and logo change. Nothing changes unless
these are set, so local and on-premise installs look the same as before.
"""

import os

from fastapi.responses import FileResponse, HTMLResponse

DEFAULT_NAME = "Agent Factory"
_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate"}

_OPEN_RECEPTIONIST = """<script>
window.addEventListener("load", function () {
  if (typeof launchAgent === "function") launchAgent("receptionist");
});
</script>
"""


def brand_name() -> str:
    return os.environ.get("BRAND_NAME", "").strip() or DEFAULT_NAME


def clinic_mode() -> bool:
    return os.environ.get("BRAND_MODE", "").strip().lower() == "clinic"


def page(path: str, *, dashboard: bool = False, headers: dict | None = None):
    """Serve one of the static pages, branded when branding is configured."""
    name = brand_name()
    if name == DEFAULT_NAME and not clinic_mode():
        return FileResponse(path, headers=headers)

    with open(path, encoding="utf-8") as fh:
        html = fh.read().replace(DEFAULT_NAME, name.replace("&", "&amp;").replace("<", "&lt;"))
    if clinic_mode():
        # Reuse the receptionist's own line (already translated) in place of the research one.
        html = html.replace(
            "Your AI-powered research platform. Pick an agent to get started.",
            "Your 24/7 virtual receptionist — answers calls and SMS, books appointments, "
            "and handles enquiries via voice or text.",
        )
        html = html.replace("<html", '<html data-brand="clinic"', 1)
        html = html.replace("</head>", '<link rel="stylesheet" href="/static/css/clinic.css?v=1">\n</head>', 1)
        if dashboard:
            html = html.replace("</body>", _OPEN_RECEPTIONIST + "</body>", 1)
    return HTMLResponse(html, headers=headers or _NO_CACHE)
