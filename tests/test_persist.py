"""deploy/persist.py: data survives a restart through a bucket (a fake one here)."""

import importlib.util
import json
import sqlite3
import tarfile
import io
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("persist", Path(__file__).parent.parent / "deploy" / "persist.py")
persist = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(persist)


class MemoryStore:
    def __init__(self):
        self.blob = None
        self.puts = 0

    def get(self):
        return self.blob

    def put(self, data):
        self.blob = data
        self.puts += 1


def _fill(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "store").mkdir(exist_ok=True)
    (folder / "store" / "contacts.json").write_text(json.dumps([{"id": 1, "name": "Alex"}]))
    (folder / "escalations.jsonl").write_text('{"reason": "URGENT: toothache"}\n')
    conn = sqlite3.connect(folder / "auth.db")
    conn.execute("CREATE TABLE users (name TEXT)")
    conn.execute("INSERT INTO users VALUES ('demo')")
    conn.commit()
    conn.close()


def test_data_survives_a_restart(tmp_path):
    store = MemoryStore()
    old = tmp_path / "before"
    _fill(old)
    assert persist.Snapshotter(store, old).snapshot() is True

    new = tmp_path / "after"          # a fresh container: empty disk
    assert persist.restore(store, new) is True
    assert json.loads((new / "store" / "contacts.json").read_text())[0]["name"] == "Alex"
    assert "toothache" in (new / "escalations.jsonl").read_text()
    conn = sqlite3.connect(new / "auth.db")
    assert conn.execute("SELECT name FROM users").fetchall() == [("demo",)]
    conn.close()


def test_nothing_is_uploaded_when_nothing_changed(tmp_path):
    store = MemoryStore()
    _fill(tmp_path)
    snapper = persist.Snapshotter(store, tmp_path)
    assert snapper.snapshot() is True
    assert snapper.snapshot() is False and store.puts == 1

    (tmp_path / "store" / "contacts.json").write_text(json.dumps([{"id": 1, "name": "Alex"}, {"id": 2}]))
    assert snapper.snapshot() is True and store.puts == 2


def test_restore_with_no_saved_copy_is_a_quiet_no_op(tmp_path):
    assert persist.restore(MemoryStore(), tmp_path / "data") is False


def test_after_restore_the_first_check_does_not_re_upload(tmp_path):
    store = MemoryStore()
    _fill(tmp_path / "a")
    persist.Snapshotter(store, tmp_path / "a").snapshot()
    persist.restore(store, tmp_path / "b")
    snapper = persist.Snapshotter(store, tmp_path / "b")
    snapper.mark_current()
    assert snapper.snapshot() is False and store.puts == 1


def test_unsafe_archive_paths_are_refused(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("../evil.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    store = MemoryStore()
    store.blob = buf.getvalue()
    with pytest.raises(RuntimeError):
        persist.restore(store, tmp_path / "data")
    assert not (tmp_path / "evil.txt").exists()


def test_unconfigured_does_nothing(monkeypatch):
    for key in ("PERSIST_S3_ENDPOINT", "PERSIST_S3_BUCKET", "PERSIST_S3_KEY_ID", "PERSIST_S3_SECRET"):
        monkeypatch.delenv(key, raising=False)
    assert persist.store_from_env() is None
    assert persist.main(["persist.py", "restore"]) == 0


def test_s3_store_treats_http_404_as_nothing_saved_and_explains_other_errors():
    try:
        from botocore.exceptions import ClientError
    except Exception:  # not installed, or an old copy that cannot import
        pytest.skip("botocore is not usable here")

    def error(status, code=""):
        return ClientError({"Error": {"Code": code, "Message": "m"}, "ResponseMetadata": {"HTTPStatusCode": status}}, "GetObject")

    class Client:
        def __init__(self, exc):
            self.exc = exc

        def get_object(self, **kw):
            raise self.exc

    store = persist.S3Store.__new__(persist.S3Store)
    store._bucket, store._key, store._endpoint = "b", "k", "https://x"
    store._client = Client(error(404))
    assert store.get() is None                      # empty code, HTTP 404: first boot

    store._client = Client(error(403, "AccessDenied"))
    with pytest.raises(RuntimeError, match="HTTP 403"):
        store.get()
    assert "bucket='b'" in store.describe() and "secret" not in store.describe().lower()
