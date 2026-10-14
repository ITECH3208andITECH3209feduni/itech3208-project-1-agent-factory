import pytest

from auth import api_keys, db, tenancy


@pytest.fixture
def organisations_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "auth_users.db"))
    db.init_db()
    tenancy.init_tenancy()

    org_a = tenancy.create_org("Organisation A", "a@example.com")
    org_b = tenancy.create_org("Organisation B", "b@example.com")

    return org_a, org_b


def test_api_key_is_hashed_at_rest(organisations_db):
    org_a, _ = organisations_db

    result = api_keys.create_api_key(
        org_id=org_a,
        label="Test key",
        created_by="admin@example.com",
    )

    assert result["key"].startswith("afk_")

    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT key_hash, org_id FROM organisation_api_keys WHERE id = ?",
            (result["id"],),
        ).fetchone()

    assert row is not None
    assert row["org_id"] == org_a
    assert row["key_hash"] == api_keys._hash_key(result["key"])
    assert row["key_hash"] != result["key"]


def test_api_key_authentication_is_org_scoped(organisations_db):
    org_a, org_b = organisations_db
    result = api_keys.create_api_key(org_a, "A key", "admin-a")

    identity = api_keys.authenticate_api_key(result["key"])

    assert identity is not None
    assert identity["org_id"] == org_a
    assert identity["role"] == "staff"
    assert api_keys.list_api_keys(org_a)[0]["id"] == result["id"]
    assert api_keys.list_api_keys(org_b) == []


def test_revoked_key_no_longer_authenticates(organisations_db):
    org_a, _ = organisations_db
    result = api_keys.create_api_key(org_a, "Revoke me", "admin")

    assert api_keys.authenticate_api_key(result["key"]) is not None
    assert api_keys.revoke_api_key(result["id"], org_a) is True
    assert api_keys.authenticate_api_key(result["key"]) is None
    assert api_keys.revoke_api_key(result["id"], org_a) is False


def test_cannot_revoke_another_organisations_key(organisations_db):
    org_a, org_b = organisations_db
    result = api_keys.create_api_key(org_a, "A key", "admin-a")

    assert api_keys.revoke_api_key(result["id"], org_b) is False
    assert api_keys.authenticate_api_key(result["key"]) is not None