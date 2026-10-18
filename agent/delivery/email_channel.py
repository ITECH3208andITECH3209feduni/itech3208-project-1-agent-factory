# agent/delivery/email_channel.py
# ──────────────────────────────────────────────────────────────
# Email delivery adapter (PROJ-429) — Dilraj Singh
#
# Outbound reminder email over plain SMTP (stdlib smtplib) — free-tier
# per the client brief ("smtp is free we can prefer it"), no paid
# email API dependency. Works with any standard SMTP provider (Gmail
# app password, SendGrid free tier, etc.).
#
# Hosts that block outgoing SMTP (Render's free plan, since September 2025)
# use Brevo's HTTPS API instead: set BREVO_API_KEY (free, 300 emails a day).
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import os
import smtplib
import socket
from email.message import EmailMessage

from agent.delivery.base import DeliveryChannel, DeliveryResult
from config.settings import (
    BREVO_API_KEY,
    EMAIL_FROM_NAME,
    SMTP_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)


def ehlo_name() -> str:
    """The name we announce to the mail server in EHLO.

    smtplib announces socket.getfqdn(). On some machines (a Mac whose address has
    no reverse-DNS name, for one) that is a long ip6.arpa string or a bare IP, and
    Gmail drops the connection ("Connection unexpectedly closed") before login.
    Use SMTP_LOCAL_HOSTNAME if set, else the machine's name when it looks like a
    real hostname, else a fixed valid one.
    """
    explicit = os.environ.get("SMTP_LOCAL_HOSTNAME", "").strip()
    if explicit:
        return explicit
    name = socket.getfqdn()
    looks_real = (
        "." in name
        and not name.lower().endswith((".arpa", ".in-addr.arpa", ".ip6.arpa"))
        and not name.replace(".", "").replace(":", "").isdigit()
        and len(name) <= 64
    )
    return name if looks_real else "agentfactory.local"


class EmailChannel(DeliveryChannel):
    name = "email"

    def __init__(self, smtp_client_factory=None):
        # Injectable for tests — defaults to the real smtplib.SMTP.
        self._smtp_client_factory = smtp_client_factory or (
            lambda: smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15, local_hostname=ehlo_name())
        )

    def is_configured(self) -> bool:
        return bool(SMTP_FROM_EMAIL and (BREVO_API_KEY or SMTP_HOST))

    def _send_once(
        self, to: str, message: str, subject: str = "Reminder", **kwargs
    ) -> DeliveryResult:
        if not self.is_configured():
            return DeliveryResult(
                ok=False,
                channel=self.name,
                to=to,
                error="Email not configured — set SMTP_HOST and "
                "SMTP_FROM_EMAIL (and SMTP_USERNAME/SMTP_PASSWORD if "
                "your provider requires auth) in .env",
                retriable=False,
            )

        if "@" not in to or to.startswith("@") or to.endswith("@"):
            return DeliveryResult(
                ok=False,
                channel=self.name,
                to=to,
                error=f"Invalid email address: {to!r}",
                retriable=False,
            )

        if BREVO_API_KEY:
            return send_via_brevo(to, subject, message)

        email_msg = EmailMessage()
        try:
            email_msg["Subject"] = subject
            email_msg["From"] = SMTP_FROM_EMAIL
            email_msg["To"] = to
            email_msg.set_content(message)
        except (ValueError, UnicodeError) as exc:
            # A malformed SMTP_FROM_EMAIL or recipient — retrying won't help.
            return DeliveryResult(
                ok=False,
                channel=self.name,
                to=to,
                error=f"Email address is not valid ({exc}). Check SMTP_FROM_EMAIL "
                "has no spaces or line breaks.",
                retriable=False,
            )

        try:
            with self._smtp_client_factory() as smtp:
                if SMTP_USE_TLS:
                    smtp.starttls()
                if SMTP_USERNAME and SMTP_PASSWORD:
                    smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.send_message(email_msg)
        except smtplib.SMTPRecipientsRefused as exc:
            return DeliveryResult(
                ok=False, channel=self.name, to=to, error=str(exc), retriable=False
            )
        except smtplib.SMTPAuthenticationError as exc:
            return DeliveryResult(
                ok=False, channel=self.name, to=to, error=str(exc), retriable=False
            )
        except UnicodeError as exc:
            # smtplib cannot encode a non-ASCII character in the login (a
            # pasted non-breaking space in the app password, for one).
            return DeliveryResult(
                ok=False,
                channel=self.name,
                to=to,
                error=f"SMTP login contains a character that is not allowed ({exc}). "
                "Re-enter SMTP_USERNAME and SMTP_PASSWORD.",
                retriable=False,
            )
        except (smtplib.SMTPException, OSError) as exc:
            # Connection resets, timeouts, transient 4xx SMTP codes —
            # worth another attempt.
            return DeliveryResult(
                ok=False, channel=self.name, to=to, error=str(exc), retriable=True
            )

        return DeliveryResult(ok=True, channel=self.name, to=to, provider_id=None)


BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def sender_name() -> str:
    return EMAIL_FROM_NAME or os.environ.get("BRAND_NAME", "").strip() or "Agent Factory"


def send_via_brevo(to: str, subject: str, message: str, post=None) -> DeliveryResult:
    """One plain-text email through Brevo's transactional API (HTTPS, port 443).

    4xx answers (bad key, unverified sender, bad address) won't fix themselves,
    so they are not retried; 429 and 5xx are."""
    import requests

    post = post or requests.post
    payload = {
        "sender": {"email": SMTP_FROM_EMAIL, "name": sender_name()},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": message,
    }
    try:
        resp = post(
            BREVO_URL,
            json=payload,
            headers={"api-key": BREVO_API_KEY, "accept": "application/json",
                     "content-type": "application/json"},
            timeout=15,
        )
    except requests.RequestException as exc:
        return DeliveryResult(ok=False, channel="email", to=to, error=f"Brevo: {exc}", retriable=True)

    if resp.status_code in (200, 201, 202):
        try:
            message_id = resp.json().get("messageId")
        except ValueError:
            message_id = None
        return DeliveryResult(ok=True, channel="email", to=to, provider_id=message_id)

    try:
        detail = resp.json().get("message") or resp.text
    except ValueError:
        detail = resp.text
    retriable = resp.status_code == 429 or resp.status_code >= 500
    return DeliveryResult(
        ok=False, channel="email", to=to,
        error=f"Brevo {resp.status_code}: {str(detail)[:200]}", retriable=retriable,
    )
