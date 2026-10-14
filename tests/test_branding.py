"""Clinic branding is opt-in; without BRAND_NAME/BRAND_MODE nothing changes."""

import pytest
from fastapi.testclient import TestClient

from app.web_ui.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_default_is_agent_factory(client, monkeypatch):
    monkeypatch.delenv("BRAND_NAME", raising=False)
    monkeypatch.delenv("BRAND_MODE", raising=False)
    html = client.get("/login").text
    assert "Agent Factory" in html and "clinic.css" not in html


def test_brand_name_replaces_the_product_name(client, monkeypatch):
    monkeypatch.setenv("BRAND_NAME", "Bright Smile Dental")
    monkeypatch.delenv("BRAND_MODE", raising=False)
    html = client.get("/login").text
    assert "Bright Smile Dental" in html and "Agent Factory" not in html
    assert "clinic.css" not in html


def test_clinic_mode_loads_the_dental_skin_on_every_page(client, monkeypatch):
    monkeypatch.setenv("BRAND_NAME", "Bright Smile Dental")
    monkeypatch.setenv("BRAND_MODE", "clinic")
    for path in ("/login", "/register", "/forgot-password", "/reset-password"):
        html = client.get(path).text
        assert 'data-brand="clinic"' in html and "/static/css/clinic.css" in html, path
        assert "Agent Factory" not in html, path


def test_clinic_dashboard_opens_the_receptionist(client, monkeypatch):
    monkeypatch.setenv("BRAND_NAME", "Bright Smile Dental")
    monkeypatch.setenv("BRAND_MODE", "clinic")
    import app.web_ui.main as main

    response = client.get("/", headers={"accept": "text/html"}, follow_redirects=False)
    # Anonymous visitors are sent to sign in; the page itself is branded when signed in.
    assert response.status_code in (200, 303)
    from app.web_ui import branding
    import os
    html = branding.page(os.path.join(main._STATIC_DIR, "index.html"), dashboard=True).body.decode()
    assert 'launchAgent("receptionist")' in html and "Bright Smile Dental" in html


def test_brand_name_is_escaped(monkeypatch):
    import os
    from app.web_ui import branding, main

    monkeypatch.setenv("BRAND_NAME", "<script>x</script>")
    html = branding.page(os.path.join(main._STATIC_DIR, "login.html")).body.decode()
    assert "<script>x</script>" not in html


def test_site_is_branded_in_clinic_mode(client, monkeypatch):
    monkeypatch.setenv("BRAND_NAME", "Bright Smile Dental")
    monkeypatch.setenv("BRAND_MODE", "clinic")
    home = client.get("/showcase").text
    assert "Bright Smile Dental" in home and "Agent Factory" not in home
    assert "\U0001F9B7" in home and "img/logo.svg" not in home

    about = client.get("/site/about.html").text
    assert "<span>Bright Smile Dental</span>" in about          # header and footer
    assert "Agent Factory was engineered as a capstone" in about  # the sentences about the project stay true
    assert "— Bright Smile Dental</title>" in about


def test_site_is_unchanged_by_default(client, monkeypatch):
    monkeypatch.delenv("BRAND_NAME", raising=False)
    monkeypatch.delenv("BRAND_MODE", raising=False)
    home = client.get("/showcase").text
    assert "Agent Factory" in home and "img/logo.svg" in home
    assert "<span>Agent Factory</span>" in client.get("/site/about.html").text
