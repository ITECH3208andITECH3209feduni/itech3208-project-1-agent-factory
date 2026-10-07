# agent/delivery/email_channel.py
# ──────────────────────────────────────────────────────────────
# Email delivery adapter (PROJ-429) — Dilraj Singh
#
# Outbound reminder email over plain SMTP (stdlib smtplib) — free-tier
# per the client brief ("smtp is free we can prefer it"), no paid
# email API dependency. Works with any standard SMTP provider (Gmail
# app password, SendGrid free tier, etc.).
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from agent.delivery.base import DeliveryChannel, DeliveryResult
from config.settings import (
    SMTP_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)


class EmailChannel(DeliveryChannel):
    name = "email"

    def __init__(self, smtp_client_factory=None):
        # Injectable for tests — defaults to the real smtplib.SMTP.
        self._smtp_client_factory = smtp_client_factory or (
            lambda: smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
        )

    def is_configured(self) -> bool:
        return bool(SMTP_HOST and SMTP_FROM_EMAIL)

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

        email_msg = EmailMessage()
        email_msg["Subject"] = subject
        email_msg["From"] = SMTP_FROM_EMAIL
        email_msg["To"] = to
        email_msg.set_content(message)

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
        except (smtplib.SMTPException, OSError) as exc:
            # Connection resets, timeouts, transient 4xx SMTP codes —
            # worth another attempt.
            return DeliveryResult(
                ok=False, channel=self.name, to=to, error=str(exc), retriable=True
            )

        return DeliveryResult(ok=True, channel=self.name, to=to, provider_id=None)
