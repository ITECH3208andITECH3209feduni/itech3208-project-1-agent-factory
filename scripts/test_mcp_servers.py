#!/usr/bin/env python3
# scripts/test_mcp_servers.py
# ──────────────────────────────────────────────────────────────
# Checks for the skill MCP servers (PROJ-324..328).
# Run: python scripts/test_mcp_servers.py
#
# Inspects the registered tools and exercises argument validation. Does not
# hit arXiv, Semantic Scholar, or Amazon — no network calls.
# ──────────────────────────────────────────────────────────────

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


def main() -> int:
    print("Skill MCP servers (PROJ-324..328)\n")

    try:
        import mcp  # noqa: F401
    except ImportError:
        print("  SKIP  mcp SDK not installed (pip install mcp)")
        return 0

    from skills.manifest_loader import get_manifest
    from skills.mcp import amazon_server, literature_server
    from skills.mcp.common import error_payload, result_to_dict, tool_description
    from skills.base_skill import SkillResult

    servers = {
        "literature": literature_server.server,
        "amazon": amazon_server.server,
    }

    # list_tools() is a coroutine in mcp 2.x.
    import asyncio

    for skill_name, srv in servers.items():
        tools = asyncio.run(srv.list_tools())
        registered = sorted(t.name for t in tools)

        manifest = get_manifest(skill_name)
        declared = sorted(t["name"] for t in manifest["tools"])

        # The manifest is published to agentskills.io; if it advertises tools the
        # server does not implement, consumers get a broken skill.
        check(
            f"{skill_name}: registered tools match the manifest",
            registered == declared,
            f"server={registered} manifest={declared}",
        )

        for tool in tools:
            check(
                f"{skill_name}.{tool.name} has a description",
                bool(tool.description) and "unavailable" not in tool.description,
                repr(tool.description)[:80],
            )
            # mcp 2.x names this input_schema; older builds used inputSchema.
            schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
            check(
                f"{skill_name}.{tool.name} exposes an object inputSchema",
                isinstance(schema, dict) and schema.get("type") == "object",
                str(schema)[:100],
            )

        check(f"{skill_name}: server has a version", bool(srv.version), srv.version)
        check(f"{skill_name}: server has instructions", bool(srv.instructions))

    # ── Description comes from the manifest, not hardcoded ────
    manifest_desc = get_manifest("literature")["tools"][0]["description"]
    check(
        "tool_description reads from the manifest",
        tool_description("literature", "literature_search") == manifest_desc,
    )
    check(
        "tool_description degrades rather than raising",
        "unavailable" in tool_description("nosuchskill", "nosuchtool"),
    )

    # ── Argument validation, no network ───────────────────────
    cases = [
        ("literature_search empty query", literature_server.literature_search, {"query": "  "}),
        ("literature_search bad max_results", literature_server.literature_search,
         {"query": "x", "max_results": 999}),
        ("literature_synthesise empty topic", literature_server.literature_synthesise, {"topic": ""}),
        ("literature_research_gaps empty topic", literature_server.literature_research_gaps,
         {"topic": ""}),
        ("literature_citations empty paper", literature_server.literature_citations, {"paper": ""}),
        ("literature_citations bad limit", literature_server.literature_citations,
         {"paper": "x", "limit": 0}),
        ("amazon_search empty query", amazon_server.amazon_search, {"query": ""}),
        ("amazon_compare empty query", amazon_server.amazon_compare, {"query": "   "}),
        ("amazon_review_sentiment empty query", amazon_server.amazon_review_sentiment, {"query": ""}),
        ("amazon_opportunity_score empty query", amazon_server.amazon_opportunity_score,
         {"query": ""}),
    ]
    for label, fn, kwargs in cases:
        out = fn(**kwargs)
        check(
            f"rejects {label}",
            isinstance(out, dict) and out.get("success") is False and bool(out.get("error")),
            str(out)[:120],
        )

    # ── result_to_dict ────────────────────────────────────────
    long_abstract = "x" * 2000
    r = SkillResult(
        skill_name="literature",
        query="q",
        success=True,
        results=[{"title": "T", "abstract": long_abstract, "empty": "", "none": None}] * 5,
        summary="s",
        metadata={"m": 1},
    )
    d = result_to_dict(r, max_results=3)
    check("result_to_dict honours max_results", d["count"] == 3, str(d["count"]))
    check("result_to_dict reports count consistently", d["count"] == len(d["results"]))
    check(
        "result_to_dict truncates long abstracts",
        len(d["results"][0]["abstract"]) < 600,
        str(len(d["results"][0]["abstract"])),
    )
    check("result_to_dict drops empty fields", "empty" not in d["results"][0])
    check("result_to_dict drops None fields", "none" not in d["results"][0])
    check("result_to_dict passes metadata through", d.get("metadata") == {"m": 1})
    check("result_to_dict omits error when absent", "error" not in d)

    failed = SkillResult(skill_name="x", query="q", success=False, error="boom", summary="s")
    check("result_to_dict surfaces error", result_to_dict(failed).get("error") == "boom")

    # ── error_payload ─────────────────────────────────────────
    e = error_payload("nope", extra=1)
    check(
        "error_payload has a consistent shape",
        e["success"] is False and e["results"] == [] and e["count"] == 0 and e["extra"] == 1,
        str(e),
    )

    # ── Logging must not touch stdout ─────────────────────────
    # On stdio transport, stdout carries JSON-RPC frames. A log line there
    # corrupts the stream and the client disconnects with a parse error.
    import logging

    stream_targets = [
        h.stream for h in logging.getLogger().handlers if hasattr(h, "stream")
    ]
    check(
        "root logging does not write to stdout",
        all(s is not sys.stdout for s in stream_targets),
        str(stream_targets),
    )

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
