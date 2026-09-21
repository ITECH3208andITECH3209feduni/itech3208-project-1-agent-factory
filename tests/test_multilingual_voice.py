# tests/test_multilingual_voice.py
# ──────────────────────────────────────────────────────────────
# Tests for PROJ-470 — Multi-language voice support.
# Covers voice_languages.py utilities and the Twilio route endpoints.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from fastapi import FastAPI


# ── Fixture ───────────────────────────────────────────────────

def _make_twilio_app():
    from app.web_ui.twilio_routes import router as twilio_router
    app = FastAPI()
    app.include_router(twilio_router)
    return app


# ── voice_languages.py unit tests ────────────────────────────

class TestVoiceLanguagesModule:

    def test_voice_map_contains_expected_languages(self):
        from app.web_ui.voice_languages import VOICE_MAP
        expected = {"en-AU", "en-US", "es-US", "hi-IN", "cmn-CN", "fr-FR", "de-DE"}
        assert expected.issubset(set(VOICE_MAP.keys()))

    def test_each_voice_is_polly(self):
        from app.web_ui.voice_languages import VOICE_MAP
        for code, voice in VOICE_MAP.items():
            assert voice.startswith("Polly."), f"Voice for {code} is not a Polly voice: {voice}"

    def test_resolve_voice_known_lang(self):
        from app.web_ui.voice_languages import resolve_voice
        voice, lang = resolve_voice("es-US")
        assert voice == "Polly.Lupe"
        assert lang == "es-US"

    def test_resolve_voice_unknown_falls_back_to_default(self):
        from app.web_ui.voice_languages import resolve_voice, DEFAULT_LANG, VOICE_MAP
        voice, lang = resolve_voice("xx-ZZ")
        assert lang == DEFAULT_LANG
        assert voice == VOICE_MAP[DEFAULT_LANG]

    def test_resolve_voice_none_falls_back_to_default(self):
        from app.web_ui.voice_languages import resolve_voice, DEFAULT_LANG, VOICE_MAP
        voice, lang = resolve_voice(None)
        assert lang == DEFAULT_LANG

    def test_detect_language_chinese(self):
        from app.web_ui.voice_languages import detect_language
        assert detect_language("你好，今天天气怎么样？") == "cmn-CN"

    def test_detect_language_hindi(self):
        from app.web_ui.voice_languages import detect_language
        assert detect_language("नमस्ते, आप कैसे हैं?") == "hi-IN"

    def test_detect_language_german(self):
        from app.web_ui.voice_languages import detect_language
        assert detect_language("Hallo, ich möchte einen Termin buchen.") == "de-DE"

    def test_detect_language_french(self):
        from app.web_ui.voice_languages import detect_language
        assert detect_language("Bonjour, je voudrais de l'aide.") == "fr-FR"

    def test_detect_language_spanish(self):
        from app.web_ui.voice_languages import detect_language
        assert detect_language("Hola, necesito ayuda por favor.") == "es-US"

    def test_detect_language_english_returns_none(self):
        from app.web_ui.voice_languages import detect_language
        # Plain English should not be detected as a non-English language
        result = detect_language("Hello, I need to book an appointment.")
        assert result is None

    def test_detect_language_empty_returns_none(self):
        from app.web_ui.voice_languages import detect_language
        assert detect_language("") is None
        assert detect_language(None) is None

    def test_list_supported_languages_structure(self):
        from app.web_ui.voice_languages import list_supported_languages
        langs = list_supported_languages()
        assert isinstance(langs, list)
        assert len(langs) >= 7
        for entry in langs:
            assert "code"  in entry
            assert "label" in entry
            assert "voice" in entry


# ── GET /twilio/voice/languages ───────────────────────────────

class TestVoiceLanguagesEndpoint:

    def setup_method(self):
        self.app    = _make_twilio_app()
        self.client = TestClient(self.app)

    def test_returns_200(self):
        resp = self.client.get("/twilio/voice/languages")
        assert resp.status_code == 200

    def test_contains_languages_list(self):
        data = self.client.get("/twilio/voice/languages").json()
        assert "languages" in data
        assert isinstance(data["languages"], list)
        assert len(data["languages"]) >= 7

    def test_contains_default(self):
        data = self.client.get("/twilio/voice/languages").json()
        assert "default" in data
        assert data["default"]  # not empty


# ── POST /twilio/voice/language ───────────────────────────────

class TestSetVoiceLanguageEndpoint:

    def setup_method(self):
        self.app    = _make_twilio_app()
        self.client = TestClient(self.app)

    def test_set_valid_language(self):
        resp = self.client.post(
            "/twilio/voice/language",
            json={"language": "fr-FR"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["language"] == "fr-FR"

    def test_set_invalid_language_returns_422(self):
        resp = self.client.post(
            "/twilio/voice/language",
            json={"language": "xx-ZZ"},
        )
        assert resp.status_code == 422

    def test_set_language_reflected_in_listing(self):
        self.client.post("/twilio/voice/language", json={"language": "de-DE"})
        data = self.client.get("/twilio/voice/languages").json()
        assert data["default"] == "de-DE"
        # Reset to default so other tests aren't affected
        self.client.post("/twilio/voice/language", json={"language": "en-AU"})


# ── POST /twilio/voice  (greeting with language) ──────────────

class TestVoiceGreetingMultiLang:

    def setup_method(self):
        self.app    = _make_twilio_app()
        self.client = TestClient(self.app)

    def test_greeting_returns_xml(self):
        resp = self.client.post("/twilio/voice", data={"CallSid": "CATEST001"})
        assert resp.status_code == 200
        assert "xml" in resp.headers["content-type"]

    def test_greeting_contains_gather(self):
        resp = self.client.post("/twilio/voice", data={"CallSid": "CATEST001"})
        assert "<Gather" in resp.text

    def test_greeting_with_lang_param(self):
        resp = self.client.post("/twilio/voice?lang=es-US", data={"CallSid": "CATEST002"})
        assert resp.status_code == 200
        # Polly.Lupe should be in the TwiML
        assert "Polly.Lupe" in resp.text

    def test_greeting_french(self):
        resp = self.client.post("/twilio/voice?lang=fr-FR", data={"CallSid": "CATEST003"})
        assert "Polly.Celine" in resp.text

    def test_greeting_hindi(self):
        resp = self.client.post("/twilio/voice?lang=hi-IN", data={"CallSid": "CATEST004"})
        assert "Polly.Aditi" in resp.text
