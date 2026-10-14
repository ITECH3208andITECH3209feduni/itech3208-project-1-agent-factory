# The CRM pages must work when mounted at /crm (as in the real app).
from fastapi.testclient import TestClient

from app.web.main import app as crm_app
from app.web_ui.main import app


def test_mounted_dashboard_calls_prefixed_api():
    html = TestClient(app).get("/crm/dashboard").text
    assert 'fetch("/crm/api/stats")' in html
    assert 'fetch("/api/stats")' not in html
    assert 'href="/crm/contacts"' in html


def test_mounted_contacts_page_links_are_prefixed():
    html = TestClient(app).get("/crm/contacts").text
    assert 'fetch("/crm/api/contacts"' in html
    assert 'href="/contacts' not in html


def test_standalone_crm_app_is_unchanged():
    html = TestClient(crm_app).get("/dashboard").text
    assert 'fetch("/api/stats")' in html
    assert "/crm/" not in html
