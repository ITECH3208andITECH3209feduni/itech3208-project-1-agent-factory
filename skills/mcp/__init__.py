"""
skills.mcp — standalone MCP servers wrapping the Agent Factory skills
(PROJ-324..328).

Each skill is exposed as its own server so it can be distributed and consumed
independently:

    python -m skills.mcp.literature_server
    python -m skills.mcp.amazon_server

Both speak stdio by default. Tool names, descriptions, and JSON Schemas come
from skills/manifests/*.skill.json, so the manifest and the running server
cannot drift apart — the manifest is the single source of truth.
"""
