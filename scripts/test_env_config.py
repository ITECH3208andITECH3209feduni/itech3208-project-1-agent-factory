#!/usr/bin/env python3
# scripts/test_env_config.py
# ──────────────────────────────────────────────────────────────
# Checks for the Sprint 3 environment hardening (PROJ-381).
# Run: python scripts/test_env_config.py
# ──────────────────────────────────────────────────────────────

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}{(' — ' + detail) if detail else ''}")


def test_override_beats_ambient() -> bool:
    """
    load_dotenv(override=True) must let the .env file win over an already
    exported shell variable. Run in a subprocess with a throwaway .env so we
    do not disturb the developer's real one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        env_file = os.path.join(tmp, ".env")
        with open(env_file, "w", encoding="utf-8") as fh:
            fh.write("AGENT_FACTORY_OVERRIDE_PROBE=from_dotenv_file\n")

        code = (
            "import os;"
            "from dotenv import load_dotenv;"
            f"load_dotenv(dotenv_path=r'{env_file}', override=True);"
            "print(os.environ['AGENT_FACTORY_OVERRIDE_PROBE'])"
        )
        env = dict(os.environ, AGENT_FACTORY_OVERRIDE_PROBE="from_shell")
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env
        )
        return out.stdout.strip() == "from_dotenv_file"


def main() -> int:
    print("Environment hardening (PROJ-381)\n")

    from config import settings

    # Every Sprint 3 variable the ticket names must exist as a setting.
    for name in (
        "BOT_TOKEN",
        "GOOGLE_CALENDAR_CREDENTIALS",
        "CHROMADB_PATH",
        "S2_API_KEY",
        "JWT_SECRET",
    ):
        check(f"settings exposes {name}", hasattr(settings, name))

    # ...and be documented in the template, or nobody will know to set it.
    with open(os.path.join(ROOT, ".env.example"), encoding="utf-8") as fh:
        example = fh.read()
    for name in (
        "ANTHROPIC_API_KEY",
        "S2_API_KEY",
        "BOT_TOKEN",
        "GOOGLE_CALENDAR_CREDENTIALS",
        "CHROMADB_PATH",
        "JWT_SECRET",
    ):
        check(f".env.example documents {name}", f"{name}=" in example)

    check("root resolved from file, not cwd", settings.PROJECT_ROOT.name != "")
    check("ENV_PATH points at project root", settings.ENV_PATH.parent == settings.PROJECT_ROOT)

    check(".env overrides ambient shell vars", test_override_beats_ambient())

    # validate_env reports rather than throws by default.
    problems = settings.validate_env()
    check("validate_env returns a list", isinstance(problems, list))

    # strict=True must raise when something is missing, and not when nothing is.
    original = settings.JWT_SECRET
    try:
        settings.JWT_SECRET = ""
        try:
            settings.validate_env(strict=True)
            check("validate_env(strict) raises on missing secret", False, "no raise")
        except RuntimeError:
            check("validate_env(strict) raises on missing secret", True)

        # A short secret is a distinct, separately reported problem.
        settings.JWT_SECRET = "tooshort"
        msgs = settings.validate_env()
        check(
            "validate_env flags short JWT_SECRET",
            any("32" in m and "JWT_SECRET" in m for m in msgs),
            f"got {msgs}",
        )

        settings.JWT_SECRET = "x" * 48
        msgs = settings.validate_env()
        check(
            "validate_env accepts a long JWT_SECRET",
            not any("JWT_SECRET" in m for m in msgs),
            f"got {msgs}",
        )
    finally:
        settings.JWT_SECRET = original

    if problems:
        print("\n  Current environment reports:")
        for p in problems:
            print(f"    - {p}")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
