"""
scripts/test_openclaw.py — OpenClaw integration smoke test.

Usage:
    python scripts/test_openclaw.py

Prints [PASS] or [FAIL] for each test.
Exits with code 0 if all tests pass, 1 if any fail.
"""

import os
import sys

# Use dummy key so the test runs without real credentials
os.environ.setdefault("PYTEST_RUNNING", "1")
os.environ.setdefault("OPENCLAW_API_KEY", "test_key")

# Ensure project root is on the path when run from any directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.openclaw.client import OpenClawWrapper
from app.openclaw.router import route_query, classify

results = []


def run_test(name: str, func):
    try:
        func()
        print(f"[PASS] {name}")
        results.append(True)
    except Exception as e:
        print(f"[FAIL] {name} — {e}")
        results.append(False)


# Test 1: OpenClawWrapper.connect() returns True
def test_connect():
    wrapper = OpenClawWrapper(api_key="test_key")
    assert wrapper.connect() is True, "connect() did not return True"

run_test("OpenClawWrapper.connect() returns True", test_connect)

# Test 2: route_query("best laptop", wrapper) returns dict with 'result' key
def test_route_amazon():
    wrapper = OpenClawWrapper(api_key="test_key")
    wrapper.connect()
    result = route_query("best laptop", wrapper)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "result" in result, f"Missing 'result' key in {result}"

run_test("route_query('best laptop') returns dict", test_route_amazon)

# Test 3: route_query("papers on AI", wrapper) returns dict with 'result' key
def test_route_literature():
    wrapper = OpenClawWrapper(api_key="test_key")
    wrapper.connect()
    result = route_query("papers on AI", wrapper)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "result" in result, f"Missing 'result' key in {result}"

run_test("route_query('papers on AI') returns dict", test_route_literature)

# Test 4: classify("buy shoes") → "amazon"
def test_classify():
    skill = classify("buy shoes")
    assert skill == "amazon", f"Expected 'amazon', got '{skill}'"

run_test("classify('buy shoes') -> 'amazon'", test_classify)

# Summary
passed = sum(results)
total = len(results)
print(f"\n{passed}/{total} tests passed")

if passed < total:
    failed = [i + 1 for i, r in enumerate(results) if not r]
    print(f"Failed tests: {failed}")
    sys.exit(1)

sys.exit(0)
