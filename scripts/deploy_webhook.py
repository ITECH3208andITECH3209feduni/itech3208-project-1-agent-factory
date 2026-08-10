#!/usr/bin/env python3
"""
scripts/deploy_webhook.py — GitHub push webhook listener (PROJ-314..318)

Runs deploy.sh when a push lands on the deploy branch.

    python scripts/deploy_webhook.py                # listen on 0.0.0.0:9000
    DEPLOY_WEBHOOK_PORT=9001 python scripts/deploy_webhook.py

Configure in .env:
    DEPLOY_WEBHOOK_SECRET   shared secret, must match the GitHub webhook
    DEPLOY_WEBHOOK_PORT     default 9000
    DEPLOY_BRANCH           branch to deploy; defaults to the current checkout

Point a GitHub webhook at http://<public-host>/deploy-hook with content type
application/json and the same secret.

Deliberately stdlib-only: this must be able to restart the container stack, so
it runs on the host outside Docker, and asking the host to carry the app's
dependencies just to receive a POST is the wrong trade.
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Read .env without a dependency on python-dotenv.
def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env()

SECRET = os.environ.get("DEPLOY_WEBHOOK_SECRET", "")
PORT   = int(os.environ.get("DEPLOY_WEBHOOK_PORT", "9000"))
BRANCH = os.environ.get("DEPLOY_BRANCH", "")
MAX_BODY = 5 * 1024 * 1024      # GitHub push payloads are well under this

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "logs" / "deploy-webhook.log"),
    ],
)
log = logging.getLogger("deploy-webhook")

# One deploy at a time. Two pushes in quick succession would otherwise have two
# deploy.sh processes fighting over the same git checkout and compose project.
_deploy_lock = threading.Lock()


def verify_signature(body: bytes, signature: str) -> bool:
    """Constant-time check of GitHub's X-Hub-Signature-256 header."""
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    # compare_digest, not ==, so a timing side channel cannot leak the secret.
    return hmac.compare_digest(expected, signature)


def run_deploy(ref: str, after: str) -> None:
    """Run deploy.sh. Called on a worker thread so the HTTP reply is not held open."""
    if not _deploy_lock.acquire(blocking=False):
        log.warning("deploy already running; ignoring push %s", after[:8])
        return
    try:
        log.info("deploying %s (%s)", ref, after[:8])
        env = dict(os.environ)
        if BRANCH:
            env["DEPLOY_BRANCH"] = BRANCH
        result = subprocess.run(
            ["bash", str(PROJECT_ROOT / "scripts" / "deploy.sh")],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if result.returncode == 0:
            log.info("deploy succeeded")
        else:
            log.error("deploy failed (exit %s)", result.returncode)
            for line in (result.stdout or "").strip().splitlines()[-15:]:
                log.error("  %s", line)
            for line in (result.stderr or "").strip().splitlines()[-15:]:
                log.error("  %s", line)
    except subprocess.TimeoutExpired:
        log.error("deploy timed out after 30 minutes")
    except Exception:
        log.exception("deploy raised")
    finally:
        _deploy_lock.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentFactoryDeployHook/1.0"

    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.client_address[0], fmt % args)

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, {"status": "ok", "deploying": _deploy_lock.locked()})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/deploy-hook":
            self._reply(404, {"error": "not found"})
            return

        # Refusing to run unauthenticated is the whole point — this endpoint
        # executes code on the host.
        if not SECRET:
            log.error("DEPLOY_WEBHOOK_SECRET is not set; refusing to process")
            self._reply(503, {"error": "server not configured"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._reply(400, {"error": "bad Content-Length"})
            return

        if length <= 0 or length > MAX_BODY:
            self._reply(413, {"error": "payload too large or empty"})
            return

        body = self.rfile.read(length)

        signature = self.headers.get("X-Hub-Signature-256", "")
        if not verify_signature(body, signature):
            log.warning("rejected: bad signature from %s", self.client_address[0])
            self._reply(401, {"error": "invalid signature"})
            return

        event = self.headers.get("X-GitHub-Event", "")
        if event == "ping":
            self._reply(200, {"status": "pong"})
            return
        if event != "push":
            self._reply(200, {"status": "ignored", "event": event})
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._reply(400, {"error": "invalid JSON"})
            return

        ref = payload.get("ref", "")
        target = BRANCH or subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
        ).stdout.strip()

        if ref != f"refs/heads/{target}":
            log.info("ignoring push to %s (deploying %s only)", ref, target)
            self._reply(200, {"status": "ignored", "ref": ref})
            return

        if payload.get("deleted"):
            self._reply(200, {"status": "ignored", "reason": "branch deleted"})
            return

        # Reply immediately; GitHub times webhook deliveries out after 10s and
        # a deploy takes minutes.
        self._reply(202, {"status": "accepted", "ref": ref})
        threading.Thread(
            target=run_deploy,
            args=(ref, payload.get("after", "")),
            daemon=True,
        ).start()


def main() -> int:
    (PROJECT_ROOT / "logs").mkdir(exist_ok=True)

    if not SECRET:
        log.warning("DEPLOY_WEBHOOK_SECRET is not set — pushes will be rejected with 503.")
        log.warning("Generate one:  python -c \"import secrets; print(secrets.token_urlsafe(32))\"")

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log.info("listening on 0.0.0.0:%d  (POST /deploy-hook, GET /health)", PORT)
    log.info("project root: %s", PROJECT_ROOT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
