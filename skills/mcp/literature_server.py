"""
skills.mcp.literature_server — LiteratureSkill as a standalone MCP server
(PROJ-324..328).

    python -m skills.mcp.literature_server                    # stdio
    python -m skills.mcp.literature_server --transport sse    # sse

Client config (e.g. .mcp.json):

    {
      "mcpServers": {
        "literature": {
          "command": "python",
          "args": ["-m", "skills.mcp.literature_server"],
          "cwd": "/path/to/itech3208-project-1-agent-factory"
        }
      }
    }
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

from skills.literature import LiteratureSkill
from skills.mcp.common import (
    error_payload,
    require_anthropic_key,
    result_to_dict,
    skill_version,
    tool_description,
)

log = logging.getLogger("mcp.literature")

SKILL = "literature"

server = MCPServer(
    name="agent-factory-literature",
    title="Agent Factory — Literature Research",
    version=skill_version(SKILL),
    instructions=(
        "Academic literature search across arXiv, Semantic Scholar, and PubMed. "
        "Use literature_search for finding papers, literature_synthesise to compare "
        "findings across a body of work, literature_research_gaps to identify what is "
        "not yet covered, and literature_citations to find papers citing a given work."
    ),
)

# One instance for the process. The Semantic Scholar token bucket is module-level
# in skills.literature, so the quota is shared correctly regardless.
_skill = LiteratureSkill()


@server.tool(name="literature_search", description=tool_description(SKILL, "literature_search"))
def literature_search(query: str, max_results: int = 10) -> dict[str, Any]:
    if not query or not query.strip():
        return error_payload("query must not be empty")
    if not 1 <= max_results <= 50:
        return error_payload("max_results must be between 1 and 50")

    try:
        # Call run() directly rather than __call__ so a failure surfaces here
        # with its real traceback instead of being flattened into SkillResult.
        result = _skill.run(query.strip())
    except Exception as exc:  # noqa: BLE001
        log.exception("literature_search failed")
        return error_payload(f"search failed: {exc}")

    return result_to_dict(result, max_results=max_results)


@server.tool(
    name="literature_synthesise", description=tool_description(SKILL, "literature_synthesise")
)
def literature_synthesise(topic: str) -> dict[str, Any]:
    if not topic or not topic.strip():
        return error_payload("topic must not be empty")

    missing = require_anthropic_key()
    if missing:
        return error_payload(missing)

    # The skill routes to synthesis on trigger keywords, so the mode is
    # selected by phrasing the query. Driving the documented interface beats
    # reaching into private mode methods that were never meant to be entered
    # mid-way.
    try:
        result = _skill.run(f"synthesise papers on {topic.strip()}")
    except Exception as exc:  # noqa: BLE001
        log.exception("literature_synthesise failed")
        return error_payload(f"synthesis failed: {exc}")

    payload = result_to_dict(result, max_results=10)
    return {
        "success": payload["success"],
        "synthesis": payload["summary"],
        "papers_analysed": payload["count"],
        **({"error": payload["error"]} if "error" in payload else {}),
    }


@server.tool(
    name="literature_research_gaps",
    description=tool_description(SKILL, "literature_research_gaps"),
)
def literature_research_gaps(topic: str) -> dict[str, Any]:
    if not topic or not topic.strip():
        return error_payload("topic must not be empty")

    missing = require_anthropic_key()
    if missing:
        return error_payload(missing)

    try:
        result = _skill.run(f"research gaps in {topic.strip()}")
    except Exception as exc:  # noqa: BLE001
        log.exception("literature_research_gaps failed")
        return error_payload(f"gap analysis failed: {exc}")

    payload = result_to_dict(result, max_results=10)
    return {
        "success": payload["success"],
        "gaps": payload["summary"],
        "papers_analysed": payload["count"],
        **({"error": payload["error"]} if "error" in payload else {}),
    }


@server.tool(
    name="literature_citations", description=tool_description(SKILL, "literature_citations")
)
def literature_citations(paper: str, limit: int = 20) -> dict[str, Any]:
    if not paper or not paper.strip():
        return error_payload("paper must not be empty")
    if not 1 <= limit <= 100:
        return error_payload("limit must be between 1 and 100")

    try:
        # This mode has a real entry point, so call it directly rather than
        # smuggling trigger words into the query.
        result = _skill._run_citation_lookup(paper.strip())
    except Exception as exc:  # noqa: BLE001
        log.exception("literature_citations failed")
        return error_payload(f"citation lookup failed: {exc}")

    payload = result_to_dict(result, max_results=limit)
    meta = result.metadata or {}
    payload["source_paper_id"] = meta.get("source_paper_id", "")
    payload["citing_count"] = meta.get("citing_count", payload["count"])
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Literature research MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport to serve on (default: stdio)",
    )
    args = parser.parse_args()

    log.info("starting literature MCP server v%s on %s", skill_version(SKILL), args.transport)
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
