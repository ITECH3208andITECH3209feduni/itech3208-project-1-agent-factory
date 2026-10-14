"""scripts/seed_demo.py leaves the analytics tab to real traffic unless asked."""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py"


def _load(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["seed_demo.py", *argv])
    spec = importlib.util.spec_from_file_location("seed_demo_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sample_analytics_are_off_by_default(monkeypatch):
    mod = _load(monkeypatch)
    assert mod.WITH_SAMPLE_ANALYTICS is False and mod.BASE == "http://localhost:8000"


def test_flag_turns_them_on_and_does_not_break_the_base_url(monkeypatch):
    mod = _load(monkeypatch, "https://demo.example.ts.net/", "--with-sample-analytics")
    assert mod.WITH_SAMPLE_ANALYTICS is True and mod.BASE == "https://demo.example.ts.net"
    mod = _load(monkeypatch, "--with-sample-analytics")
    assert mod.BASE == "http://localhost:8000"
