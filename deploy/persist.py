#!/usr/bin/env python3
"""Keep the app's data across restarts on a host with no persistent disk (Render free).

The whole data folder (SQLite databases, the JSON tables that hold contacts and
reminders, the escalation log) is packed into one archive and stored in any
S3-compatible bucket (Backblaze B2, Cloudflare R2, ...). On start it is restored
before anything opens a database; while running it is re-saved whenever
something changed, and once more when the container is told to stop.

    python deploy/persist.py restore    # download and unpack, if a saved copy exists
    python deploy/persist.py snapshot   # save now, if anything changed
    python deploy/persist.py loop       # save every PERSIST_INTERVAL seconds (default 60)

Settings (environment). With any of the first four missing, everything here does
nothing, so local and on-premise installs are unaffected:

    PERSIST_S3_ENDPOINT   e.g. https://s3.us-west-004.backblazeb2.com
    PERSIST_S3_BUCKET     a private bucket
    PERSIST_S3_KEY_ID     application key id
    PERSIST_S3_SECRET     application key
    PERSIST_S3_REGION     optional, default "auto"
    PERSIST_S3_PREFIX     optional folder in the bucket, default "agent-factory"
    PERSIST_DIR           data folder, default /data
    PERSIST_INTERVAL      seconds between checks, default 60
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import sqlite3
import sys
import tarfile
import tempfile
import time
from pathlib import Path

log = logging.getLogger("persist")

_SKIP_SUFFIXES = (".tmp", "-wal", "-shm", "-journal")


class S3Store:
    """One object in an S3-compatible bucket."""

    def __init__(self, endpoint: str, bucket: str, key_id: str, secret: str, region: str, key: str):
        import boto3  # imported here so unconfigured installs never need it
        from botocore.config import Config

        self._client = boto3.client(
            "s3",
            config=Config(s3={"addressing_style": "path"}),  # works on B2, R2, Supabase, MinIO
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            region_name=region,
        )
        self._bucket = bucket
        self._key = key

    def get(self) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            return self._client.get_object(Bucket=self._bucket, Key=self._key)["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
                return None
            raise

    def put(self, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=self._key, Body=data)


def store_from_env(env=os.environ) -> S3Store | None:
    needed = ("PERSIST_S3_ENDPOINT", "PERSIST_S3_BUCKET", "PERSIST_S3_KEY_ID", "PERSIST_S3_SECRET")
    if not all(env.get(k, "").strip() for k in needed):
        return None
    prefix = env.get("PERSIST_S3_PREFIX", "agent-factory").strip().strip("/")
    return S3Store(
        env["PERSIST_S3_ENDPOINT"].strip(),
        env["PERSIST_S3_BUCKET"].strip(),
        env["PERSIST_S3_KEY_ID"].strip(),
        env["PERSIST_S3_SECRET"].strip(),
        env.get("PERSIST_S3_REGION", "auto").strip() or "auto",
        f"{prefix}/data.tar.gz",
    )


def _files(data_dir: Path):
    for path in sorted(data_dir.rglob("*")):
        if path.is_file() and not path.name.endswith(_SKIP_SUFFIXES):
            yield path


def _copy_for_snapshot(path: Path, tmp: Path, rel: Path) -> Path:
    """A consistent copy: SQLite files go through the backup API, not a raw copy
    that could catch a write half-done. JSON tables are written by rename, so a
    plain copy is whole."""
    dest = tmp / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".db":
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(dest)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    else:
        dest.write_bytes(path.read_bytes())
    return dest


def build_snapshot(data_dir: Path) -> tuple[bytes, str]:
    """(archive bytes, content hash). The hash ignores timestamps so an unchanged
    folder hashes the same every time."""
    digest = hashlib.sha256()
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for path in _files(data_dir):
                rel = path.relative_to(data_dir)
                copy = _copy_for_snapshot(path, tmp, rel)
                digest.update(str(rel).encode())
                digest.update(copy.read_bytes())
                tar.add(copy, arcname=str(rel))
    return buf.getvalue(), digest.hexdigest()


def restore(store, data_dir: Path) -> bool:
    """Unpack the saved copy into data_dir. False when there is none yet."""
    blob = store.get()
    if blob is None:
        log.info("persist: no saved copy yet, starting empty")
        return False
    data_dir.mkdir(parents=True, exist_ok=True)
    root = data_dir.resolve()
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar.getmembers():
            target = (root / member.name).resolve()
            if not member.isfile() or root not in target.parents:
                raise RuntimeError(f"persist: refusing unsafe archive member {member.name!r}")
        for member in tar.getmembers():
            target = root / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
    log.info("persist: restored saved data into %s", data_dir)
    return True


class Snapshotter:
    def __init__(self, store, data_dir: Path):
        self.store = store
        self.data_dir = data_dir
        self._last_hash: str | None = None

    def snapshot(self) -> bool:
        """Save if anything changed. True when something was uploaded."""
        if not self.data_dir.exists():
            return False
        blob, digest = build_snapshot(self.data_dir)
        if digest == self._last_hash:
            return False
        self.store.put(blob)
        self._last_hash = digest
        log.info("persist: saved %d bytes", len(blob))
        return True

    def mark_current(self) -> None:
        """After a restore, the folder matches what is stored: nothing to upload yet."""
        if self.data_dir.exists():
            self._last_hash = build_snapshot(self.data_dir)[1]


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    command = argv[1] if len(argv) > 1 else ""
    store = store_from_env()
    if store is None:
        log.info("persist: no PERSIST_S3_* settings, data stays on this machine only")
        return 0

    data_dir = Path(os.environ.get("PERSIST_DIR", "/data"))
    snapper = Snapshotter(store, data_dir)

    try:
        if command == "restore":
            restore(store, data_dir)
        elif command == "snapshot":
            snapper.snapshot()
        elif command == "loop":
            interval = max(10, int(os.environ.get("PERSIST_INTERVAL", "60")))
            snapper.mark_current()
            while True:
                time.sleep(interval)
                try:
                    snapper.snapshot()
                except Exception:  # a failed save must not stop the next try
                    log.exception("persist: save failed, will retry")
        else:
            print(__doc__)
            return 2
    except Exception:
        log.exception("persist: %s failed", command)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
