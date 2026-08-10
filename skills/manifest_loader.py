# skills/manifest_loader.py
# ──────────────────────────────────────────────────────────────
# Discovery and validation of skill manifests (PROJ-329..333).
#
# Manifests live in skills/manifests/<name>.skill.json and describe a skill
# for distribution: identity, semver, tools with JSON Schema, and how to run
# it as an MCP server.
#
# Validation is deliberately dependency-free. jsonschema would be stricter,
# but the registry endpoint and the MCP servers both import this at startup,
# and adding a hard dependency to serve a JSON file is a poor trade. The
# checks below cover the mistakes that actually happen: bad semver, a name
# that disagrees with the code, duplicate tool names, malformed inputSchema.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MANIFEST_DIR = Path(__file__).resolve().parent / "manifests"
SCHEMA_PATH  = Path(__file__).resolve().parent / "schema" / "skill.schema.json"

SUPPORTED_MANIFEST_VERSIONS = {"0.1"}

# Official semver pattern (semver.org).
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
NAME_RE      = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ENV_NAME_RE  = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ManifestError(ValueError):
    """A manifest is malformed or internally inconsistent."""


def validate_manifest(data: dict[str, Any], source: str = "<dict>") -> list[str]:
    """
    Return a list of problems. Empty means valid.

    Collects every problem rather than raising on the first, so fixing a
    manifest is one pass instead of a guessing game.
    """
    problems: list[str] = []

    def require(field: str) -> bool:
        if field not in data:
            problems.append(f"{source}: missing required field '{field}'")
            return False
        return True

    for field in ("manifestVersion", "name", "version", "description", "author", "tools"):
        require(field)

    mv = data.get("manifestVersion")
    if mv is not None and mv not in SUPPORTED_MANIFEST_VERSIONS:
        problems.append(
            f"{source}: manifestVersion '{mv}' is not supported "
            f"(expected one of {sorted(SUPPORTED_MANIFEST_VERSIONS)})"
        )

    name = data.get("name")
    if name is not None and not NAME_RE.match(str(name)):
        problems.append(f"{source}: name '{name}' must be lowercase alphanumeric with hyphens")

    version = data.get("version")
    if version is not None and not SEMVER_RE.match(str(version)):
        problems.append(f"{source}: version '{version}' is not valid semver")

    desc = data.get("description", "")
    if desc and not (20 <= len(desc) <= 600):
        problems.append(f"{source}: description must be 20-600 chars, got {len(desc)}")

    author = data.get("author")
    if isinstance(author, dict):
        if not author.get("name"):
            problems.append(f"{source}: author.name is required")
    elif author is not None:
        problems.append(f"{source}: author must be an object")

    runtime = data.get("runtime")
    if isinstance(runtime, dict):
        if runtime.get("type") not in ("python", "node"):
            problems.append(f"{source}: runtime.type must be 'python' or 'node'")
        entry = runtime.get("entryPoint", "")
        if ":" not in entry:
            problems.append(f"{source}: runtime.entryPoint should be 'module.path:ClassName'")

    mcp = data.get("mcp")
    if isinstance(mcp, dict):
        if mcp.get("transport") not in ("stdio", "sse", "http"):
            problems.append(f"{source}: mcp.transport must be stdio, sse, or http")
        if not mcp.get("server"):
            problems.append(f"{source}: mcp.server is required when mcp is present")

    for cfg in data.get("configuration", []) or []:
        cname = cfg.get("name", "")
        if not ENV_NAME_RE.match(str(cname)):
            problems.append(f"{source}: configuration name '{cname}' must be UPPER_SNAKE_CASE")
        if "required" not in cfg:
            problems.append(f"{source}: configuration '{cname}' must declare 'required'")

    tools = data.get("tools")
    if isinstance(tools, list):
        if not tools:
            problems.append(f"{source}: tools must not be empty")
        seen: set[str] = set()
        for i, tool in enumerate(tools):
            label = f"{source}: tools[{i}]"
            if not isinstance(tool, dict):
                problems.append(f"{label} must be an object")
                continue

            tname = tool.get("name", "")
            if not TOOL_NAME_RE.match(str(tname)):
                problems.append(f"{label} name '{tname}' must be lower_snake_case")
            # Duplicate tool names silently shadow each other at dispatch —
            # a bug that is very hard to spot at runtime.
            if tname in seen:
                problems.append(f"{label} duplicate tool name '{tname}'")
            seen.add(tname)

            tdesc = tool.get("description", "")
            if len(tdesc) < 20:
                problems.append(
                    f"{label} ('{tname}') description is too short; a model uses it to "
                    f"decide whether to call the tool"
                )

            schema = tool.get("inputSchema")
            if not isinstance(schema, dict):
                problems.append(f"{label} ('{tname}') inputSchema is required")
                continue
            if schema.get("type") != "object":
                problems.append(f"{label} ('{tname}') inputSchema.type must be 'object'")
            props = schema.get("properties")
            if not isinstance(props, dict):
                problems.append(f"{label} ('{tname}') inputSchema.properties must be an object")
                continue
            for req in schema.get("required", []):
                if req not in props:
                    problems.append(
                        f"{label} ('{tname}') requires '{req}' but does not define it in properties"
                    )
    elif tools is not None:
        problems.append(f"{source}: tools must be an array")

    return problems


def load_manifest(path: Path, strict: bool = True) -> dict[str, Any]:
    """Load and validate one manifest. Raises ManifestError when strict."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{path.name}: invalid JSON — {exc}") from exc

    problems = validate_manifest(data, source=path.name)
    if problems and strict:
        raise ManifestError("\n  - ".join([f"{path.name} is invalid:"] + problems))

    data["_source"] = path.name
    return data


def discover_manifests(strict: bool = False) -> list[dict[str, Any]]:
    """
    Load every manifest in skills/manifests/, sorted by name.

    strict=False by default: one broken manifest should not take down the
    whole registry endpoint. Invalid manifests are returned with an
    `_errors` key so callers can surface them instead of hiding them.
    """
    if not MANIFEST_DIR.is_dir():
        return []

    out: list[dict[str, Any]] = []
    for path in sorted(MANIFEST_DIR.glob("*.skill.json")):
        try:
            data = load_manifest(path, strict=strict)
        except ManifestError as exc:
            if strict:
                raise
            out.append({"name": path.stem.replace(".skill", ""), "_source": path.name,
                        "_errors": [str(exc)]})
            continue

        problems = validate_manifest(data, source=path.name)
        if problems:
            data["_errors"] = problems
        out.append(data)

    return out


def get_manifest(name: str) -> dict[str, Any] | None:
    """Return the manifest for `name`, or None."""
    for m in discover_manifests():
        if m.get("name") == name:
            return m
    return None


def list_tools() -> list[dict[str, Any]]:
    """Flatten every tool across every skill, tagged with its owning skill."""
    tools: list[dict[str, Any]] = []
    for m in discover_manifests():
        for tool in m.get("tools", []) or []:
            tools.append({**tool, "skill": m.get("name"), "skillVersion": m.get("version")})
    return tools
