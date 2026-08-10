#!/usr/bin/env python3
# scripts/test_deploy_webhook.py
# ──────────────────────────────────────────────────────────────
# Checks for the deploy webhook listener (PROJ-314..318).
# Run: python scripts/test_deploy_webhook.py
#
# Starts the real server on a scratch port with deploy execution stubbed out,
# so nothing is actually pulled, built, or restarted.
# ──────────────────────────────────────────────────────────────

import hashlib
import hmac
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

SECRET = "test-secret-do-not-use"
PORT = 18099

os.environ["DEPLOY_WEBHOOK_SECRET"] = SECRET
os.environ["DEPLOY_BRANCH"] = "master"

import deploy_webhook as dw  # noqa: E402

dw.SECRET = SECRET
dw.BRANCH = "master"

# Record deploys instead of running them.
DEPLOYS = []
dw.run_deploy = lambda ref, after: DEPLOYS.append((ref, after))

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}{(' — ' + detail) if detail else ''}")


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post(body: bytes, signature=None, event="push", path="/deploy-hook"):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=body, method="POST"
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("X-GitHub-Event", event)
    if signature is not None:
        req.add_header("X-Hub-Signature-256", signature)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def get(path="/health"):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main() -> int:
    print("Deploy webhook listener (PROJ-314..318)\n")

    server = ThreadingHTTPServer(("127.0.0.1", PORT), dw.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.4)

    try:
        push = json.dumps({"ref": "refs/heads/master", "after": "a" * 40}).encode()

        # ── Signature verification ────────────────────────────
        code, _ = post(push, sign(push))
        check("valid signature accepted", code == 202, f"got {code}")

        code, _ = post(push, "sha256=" + "0" * 64)
        check("wrong signature rejected", code == 401, f"got {code}")

        code, _ = post(push, None)
        check("missing signature rejected", code == 401, f"got {code}")

        code, _ = post(push, "garbage")
        check("malformed signature rejected", code == 401, f"got {code}")

        code, _ = post(push, sign(push, "wrong-secret"))
        check("signature from wrong secret rejected", code == 401, f"got {code}")

        # A valid signature over *different* content must not pass.
        other = json.dumps({"ref": "refs/heads/master", "after": "b" * 40}).encode()
        code, _ = post(other, sign(push))
        check("signature bound to body", code == 401, f"got {code}")

        # ── Event and branch filtering ────────────────────────
        code, body = post(push, sign(push), event="ping")
        check("ping answered with pong", code == 200 and body.get("status") == "pong", str(body))

        code, body = post(push, sign(push), event="issues")
        check("non-push event ignored", body.get("status") == "ignored", str(body))

        wrong_branch = json.dumps({"ref": "refs/heads/feature-x", "after": "c" * 40}).encode()
        code, body = post(wrong_branch, sign(wrong_branch))
        check("push to other branch ignored", body.get("status") == "ignored", str(body))

        deleted = json.dumps(
            {"ref": "refs/heads/master", "after": "0" * 40, "deleted": True}
        ).encode()
        code, body = post(deleted, sign(deleted))
        check("branch deletion ignored", body.get("status") == "ignored", str(body))

        # ── Malformed input ───────────────────────────────────
        bad = b"{not json"
        code, _ = post(bad, sign(bad))
        check("invalid JSON rejected", code == 400, f"got {code}")

        code, _ = post(b"", sign(b""))
        check("empty body rejected", code == 413, f"got {code}")

        # ── Routing ───────────────────────────────────────────
        code, _ = post(push, sign(push), path="/wrong")
        check("unknown path 404s", code == 404, f"got {code}")

        code, body = get("/health")
        check("health endpoint responds", code == 200 and body.get("status") == "ok", str(body))

        code, _ = get("/wrong")
        check("unknown GET path 404s", code == 404, f"got {code}")

        # ── Unconfigured secret ───────────────────────────────
        saved = dw.SECRET
        dw.SECRET = ""
        code, _ = post(push, sign(push))
        check("refuses to run without a configured secret", code == 503, f"got {code}")
        dw.SECRET = saved

        # ── Only real pushes triggered a deploy ───────────────
        check(
            "exactly one deploy triggered",
            len(DEPLOYS) == 1,
            f"got {len(DEPLOYS)}: {DEPLOYS}",
        )
        check(
            "deploy received the right ref",
            DEPLOYS and DEPLOYS[0][0] == "refs/heads/master",
            str(DEPLOYS),
        )
    finally:
        server.shutdown()

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
