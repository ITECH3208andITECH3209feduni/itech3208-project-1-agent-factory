# tests/api/conftest.py
import pytest

TEST_API_KEY = "test-api-key-for-pytest"


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", TEST_API_KEY)