# tests/test_web_contacts_dashboard_pytest_wrappers.py
# ──────────────────────────────────────────────────────────────
# Wires scripts/test_contacts.py, test_dashboard.py, and
# test_reminders_list.py (PROJ-417-421, 437-441) into pytest/CI.
#
# Those scripts were written as standalone PASS/FAIL harnesses
# (`python scripts/test_X.py`, own check() counter, main() -> int),
# not as pytest test functions — so `pytest` never discovered or
# ran them, and neither did CI. Rather than rewrite each internal
# check as a separate test_* function (rewriting verification logic
# someone else wrote is its own way to introduce bugs), each wrapper
# below just runs the script's own main() and asserts it reported
# zero failures — the exact same checks, now actually wired in.
# ──────────────────────────────────────────────────────────────

import importlib.util
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_ROOT, "scripts")


def _run_script_main(script_name: str) -> int:
    path = os.path.join(_SCRIPTS, script_name)
    spec = importlib.util.spec_from_file_location(script_name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.main()


def test_contacts_script_all_checks_pass():
    assert _run_script_main("test_contacts.py") == 0


def test_dashboard_script_all_checks_pass():
    assert _run_script_main("test_dashboard.py") == 0


def test_reminders_list_script_all_checks_pass():
    assert _run_script_main("test_reminders_list.py") == 0
