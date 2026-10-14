# app/web_ui/voice_languages.py
# ──────────────────────────────────────────────────────────────
# Multi-language voice support for the AI Receptionist.
# PROJ-453 (Real-Time Dashboard & Receptionist Enhancements)
# PROJ-470 (Multi-language voice support — Part D, optional)
#
# Provides:
#   VOICE_MAP          — BCP-47 tag → Twilio Polly voice name
#   VOICE_LANGUAGE_MAP — BCP-47 tag → Twilio Gather/Say language code
#   detect_language()  — heuristic keyword/phrase detector
#   resolve_voice()    — pick voice + language pair from a lang code
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import re

# ── Supported language → Polly voice mapping ─────────────────────────────────
# Keys are BCP-47 tags that match Twilio's `language=` and `voice=` parameters.
VOICE_MAP: dict[str, str] = {
    "en-AU":  "Polly.Nicole",     # Australian English  (female)
    "en-US":  "Polly.Joanna",     # American English    (female)
    "es-US":  "Polly.Lupe",       # US Spanish          (female)
    "hi-IN":  "Polly.Aditi",      # Hindi               (female)
    "cmn-CN": "Polly.Zhiyu",      # Mandarin Chinese    (female)
    "fr-FR":  "Polly.Celine",     # French              (female)
    "de-DE":  "Polly.Marlene",    # German              (female)
}

# Twilio Gather/Say language codes (same as voice key in all our cases)
VOICE_LANGUAGE_MAP: dict[str, str] = {k: k for k in VOICE_MAP}

# Default when nothing can be determined
DEFAULT_LANG = "en-AU"

# ── Heuristic keyword → language detection ────────────────────────────────────
# Ordered from most-specific to least-specific.
_LANG_PATTERNS: list[tuple[str, list[str]]] = [
    # Chinese — unique characters
    ("cmn-CN", [r"[\u4e00-\u9fff]"]),
    # Hindi — Devanagari script
    ("hi-IN",  [r"[\u0900-\u097f]"]),
    # German — distinctive words
    ("de-DE",  [
        r"\b(hallo|guten|bitte|danke|sprechen|hilfe|termin|buchen|anruf|schlie[ßs]en)\b"
    ]),
    # French — distinctive words
    ("fr-FR",  [
        r"\b(bonjour|merci|s'il vous pla[iî]t|parler|aide|rendez.vous|appel|au revoir)\b"
    ]),
    # Spanish — distinctive words
    ("es-US",  [
        r"\b(hola|gracias|ayuda|hablar|cita|llamada|adi[oó]s|por favor|buenos d[ií]as)\b"
    ]),
]


def detect_language(text: str) -> str | None:
    """
    Inspect `text` for language-specific patterns and return a BCP-47 tag,
    or None if the text looks like plain English (or is undetectable).
    """
    if not text or not text.strip():
        return None
    for lang, patterns in _LANG_PATTERNS:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return lang
    return None


def resolve_voice(lang_code: str | None) -> tuple[str, str]:
    """
    Given a BCP-47 language code (possibly None or unknown),
    return ``(polly_voice, twilio_language)`` to use in Twilio TwiML.

    Falls back to ``DEFAULT_LANG`` for unsupported tags.
    """
    code = (lang_code or DEFAULT_LANG).strip()
    if code not in VOICE_MAP:
        code = DEFAULT_LANG
    return VOICE_MAP[code], VOICE_LANGUAGE_MAP[code]


def list_supported_languages() -> list[dict]:
    """Return the full list of supported language entries for the API."""
    labels = {
        "en-AU":  "English (Australian)",
        "en-US":  "English (US)",
        "es-US":  "Spanish (US)",
        "hi-IN":  "Hindi",
        "cmn-CN": "Mandarin Chinese",
        "fr-FR":  "French",
        "de-DE":  "German",
    }
    return [
        {
            "code":  code,
            "label": labels.get(code, code),
            "voice": voice,
        }
        for code, voice in VOICE_MAP.items()
    ]
