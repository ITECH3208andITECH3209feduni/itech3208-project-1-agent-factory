"""
skills.mcp.amazon_server — AmazonSkill as a standalone MCP server
(PROJ-324..328).

    python -m skills.mcp.amazon_server                    # stdio
    python -m skills.mcp.amazon_server --transport sse    # sse

Client config (e.g. .mcp.json):

    {
      "mcpServers": {
        "amazon": {
          "command": "python",
          "args": ["-m", "skills.mcp.amazon_server"],
          "cwd": "/path/to/itech3208-project-1-agent-factory"
        }
      }
    }

These tools drive a headless Chromium via Playwright, so calls take seconds
rather than milliseconds and can come back empty under bot detection.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

from skills.amazon import AmazonSkill
from skills.mcp.common import (
    error_payload,
    require_anthropic_key,
    result_to_dict,
    skill_version,
    tool_description,
)

log = logging.getLogger("mcp.amazon")

SKILL = "amazon"

server = MCPServer(
    name="agent-factory-amazon",
    title="Agent Factory — Amazon Product Research",
    version=skill_version(SKILL),
    instructions=(
        "Amazon product research. Use amazon_search to find products, amazon_compare "
        "to weigh several options against each other, amazon_review_sentiment to "
        "understand what buyers actually complain about, and amazon_opportunity_score "
        "to assess a niche from a seller's perspective. Results come from scraping, "
        "so they can be slow and occasionally empty."
    ),
)

# One instance per process so the Playwright browser is launched once and
# reused; AmazonSkill caches it on the class.
_skill = AmazonSkill()


@server.tool(name="amazon_search", description=tool_description(SKILL, "amazon_search"))
def amazon_search(query: str) -> dict[str, Any]:
    if not query or not query.strip():
        return error_payload("query must not be empty")

    try:
        # Direct call to the search mode, bypassing keyword routing — otherwise
        # a query like "compare headphones" would silently run comparison
        # instead of the search the caller asked for.
        result = _skill._run_normal_search(query.strip())
    except Exception as exc:  # noqa: BLE001
        log.exception("amazon_search failed")
        return error_payload(f"search failed: {exc}")

    return result_to_dict(result)


@server.tool(name="amazon_compare", description=tool_description(SKILL, "amazon_compare"))
def amazon_compare(query: str) -> dict[str, Any]:
    if not query or not query.strip():
        return error_payload("query must not be empty")

    try:
        result = _skill._run_comparison(query.strip())
    except Exception as exc:  # noqa: BLE001
        log.exception("amazon_compare failed")
        return error_payload(f"comparison failed: {exc}")

    return result_to_dict(result)


@server.tool(
    name="amazon_review_sentiment", description=tool_description(SKILL, "amazon_review_sentiment")
)
def amazon_review_sentiment(query: str) -> dict[str, Any]:
    if not query or not query.strip():
        return error_payload("query must not be empty")

    missing = require_anthropic_key()
    if missing:
        return error_payload(missing)

    try:
        result = _skill._run_review_analysis(query.strip())
    except Exception as exc:  # noqa: BLE001
        log.exception("amazon_review_sentiment failed")
        return error_payload(f"sentiment analysis failed: {exc}")

    payload = result_to_dict(result)
    payload["sentiment"] = (result.metadata or {}).get("sentiment", {})
    return payload


@server.tool(
    name="amazon_opportunity_score",
    description=tool_description(SKILL, "amazon_opportunity_score"),
)
def amazon_opportunity_score(query: str) -> dict[str, Any]:
    if not query or not query.strip():
        return error_payload("query must not be empty")

    missing = require_anthropic_key()
    if missing:
        return error_payload(missing)

    try:
        result = _skill._run_opportunity_score(query.strip())
    except Exception as exc:  # noqa: BLE001
        log.exception("amazon_opportunity_score failed")
        return error_payload(f"opportunity scoring failed: {exc}")

    return result_to_dict(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Amazon product research MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport to serve on (default: stdio)",
    )
    args = parser.parse_args()

    log.info("starting amazon MCP server v%s on %s", skill_version(SKILL), args.transport)
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
