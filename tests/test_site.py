# tests/test_site.py
# ──────────────────────────────────────────────────────────────
# Unit and integration tests for Information Website & Deploy Pipeline
# PROJ-403 (Epic: Information Website)
# PROJ-447 (Site structure + copywriting: info-only, no trial/signup)
# PROJ-448 (Static site build: home, features, pricing pages)
# PROJ-449 (Responsive layout + branding pass)
# PROJ-450 (GitHub Pages hosting + deploy pipeline)
# PROJ-451 (Automatic FAQ page: written format)
# ──────────────────────────────────────────────────────────────

import os
import yaml
import pytest
from fastapi.testclient import TestClient
from app.web_ui.main import app

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SITE_DIR = os.path.join(_PROJECT_ROOT, "site")


@pytest.fixture
def client():
    return TestClient(app)


def test_site_files_exist():
    """Verify all mandatory static site files exist (PROJ-448)."""
    required_files = [
        "index.html",
        "features.html",
        "pricing.html",
        "about.html",
        "faq.html",
        "css/site.css",
        "js/site.js",
    ]
    for rel_path in required_files:
        full_path = os.path.join(_SITE_DIR, rel_path)
        assert os.path.exists(full_path), f"Missing required site file: {rel_path}"
        assert os.path.getsize(full_path) > 0, f"Empty site file: {rel_path}"


def test_site_copywriting_info_only():
    """Verify site has no fake trial/signup forms and is info-only (PROJ-447)."""
    pricing_path = os.path.join(_SITE_DIR, "pricing.html")
    with open(pricing_path, "r", encoding="utf-8") as f:
        content = f.read().lower()

    # Must confirm info-only nature
    assert "no paywalls" in content or "no trial signups" in content
    assert "form action" not in content  # No payment or signup forms


def test_site_faq_written_format():
    """Verify FAQ page has search input, categories, and rich questions (PROJ-451)."""
    faq_path = os.path.join(_SITE_DIR, "faq.html")
    with open(faq_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'id="faq-search-input"' in content
    assert 'class="category-chip' in content
    assert "Twilio" in content
    assert "arXiv" in content
    assert "bounces" in content or "bounce" in content


def test_github_pages_workflow_syntax():
    """Verify GitHub Pages deploy workflow is valid YAML with proper configuration (PROJ-450)."""
    workflow_path = os.path.join(_PROJECT_ROOT, ".github", "workflows", "deploy-pages.yml")
    assert os.path.exists(workflow_path), "Missing deploy-pages.yml workflow file"

    with open(workflow_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "jobs" in data
    assert "deploy" in data["jobs"]
    assert "steps" in data["jobs"]["deploy"]
    # Verify pages upload path points to site
    steps = data["jobs"]["deploy"]["steps"]
    upload_step = next((s for s in steps if "upload-pages-artifact" in s.get("uses", "")), None)
    assert upload_step is not None
    assert upload_step.get("with", {}).get("path") == "./site"


def test_fastapi_serves_showcase_and_subpages(client):
    """Verify FastAPI routes /showcase and /site deliver the static site pages (PROJ-448)."""
    resp_home = client.get("/showcase")
    assert resp_home.status_code == 200
    assert "Agent Factory" in resp_home.text

    for page in ["features", "pricing", "about", "faq"]:
        resp = client.get(f"/site/{page}")
        assert resp.status_code == 200
        assert "Agent Factory" in resp.text
