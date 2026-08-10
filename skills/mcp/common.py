"""
skills.mcp.common — shared plumbing for the skill MCP servers (PROJ-324..328).

Holds the parts both servers need: turning a SkillResult into a JSON-safe
dict, reading tool descriptions out of the manifest, and a uniform error
shape.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from skills.base_skill import SkillResult
from skills.manifest_loader import get_manifest

# stderr, never stdout. On a stdio transport, stdout carries the JSON-RPC
# frames — a stray print() there corrupts the protocol stream and the client
# disconnects with an opaque parse error.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)


def tool_description(skill: str, tool: str) -> str:
    """
    Pull a tool's description from the manifest.

    Keeping descriptions in one place means the published manifest and the
    live server always agree. Falls back to a placeholder rather than raising
    — a missing description should degrade the server, not prevent it starting.
    """
    manifest = get_manifest(skill)
    if manifest:
        for entry in manifest.get("tools", []) or []:
            if entry.get("name") == tool:
                return entry.get("description", "")
    return f"{tool} (description unavailable — manifest missing or malformed)"


def skill_version(skill: str) -> str:
    manifest = get_manifest(skill)
    return (manifest or {}).get("version", "0.0.0")


def result_to_dict(result: SkillResult, max_results: int | None = None) -> dict[str, Any]:
    """
    Convert a SkillResult into a JSON-safe payload matching the manifest's
    outputSchema.

    Abstracts are truncated: some arXiv abstracts run to thousands of
    characters and ten of them will swamp the caller's context for no benefit.
    """
    items = result.results or []
    if max_results is not None:
        items = items[:max_results]

    cleaned: list[dict[str, Any]] = []
    for item in items:
        entry = {k: v for k, v in item.items() if v not in (None, "")}
        abstract = entry.get("abstract")
        if isinstance(abstract, str) and len(abstract) > 500:
            entry["abstract"] = abstract[:500].rstrip() + "…"
        cleaned.append(entry)

    payload: dict[str, Any] = {
        "success": bool(result.success),
        "summary": result.summary or "",
        "count":   len(cleaned),
        "results": cleaned,
    }
    if result.error:
        payload["error"] = result.error
    if result.metadata:
        payload["metadata"] = result.metadata
    return payload


def error_payload(message: str, **extra: Any) -> dict[str, Any]:
    """
    Uniform failure shape.

    Returned as a normal result rather than raised: a model calling the tool
    can read and act on `error`, whereas a protocol-level exception just
    surfaces as an opaque failure.
    """
    return {"success": False, "summary": message, "count": 0, "results": [], "error": message, **extra}


def require_anthropic_key() -> str | None:
    """Return an error message if the Claude key is missing, else None."""
    from config.settings import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "YOUR_API_KEY_HERE":
        return (
            "ANTHROPIC_API_KEY is not configured, so this tool cannot run. "
            "Set it in .env. Plain search tools work without it."
        )
    return None
