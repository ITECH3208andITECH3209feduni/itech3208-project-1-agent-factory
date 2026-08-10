#!/usr/bin/env python3
# scripts/test_manifests.py
# ──────────────────────────────────────────────────────────────
# Checks for skill manifests and the loader (PROJ-329..333).
# Run: python scripts/test_manifests.py
# ──────────────────────────────────────────────────────────────

import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from skills.manifest_loader import (  # noqa: E402
    MANIFEST_DIR,
    SCHEMA_PATH,
    ManifestError,
    discover_manifests,
    get_manifest,
    list_tools,
    load_manifest,
    validate_manifest,
)

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
    print("Skill manifests (PROJ-329..333)\n")

    # ── Discovery ─────────────────────────────────────────────
    manifests = discover_manifests()
    check("discovers manifests", len(manifests) >= 2, f"found {len(manifests)}")

    names = sorted(m.get("name") for m in manifests)
    check("finds literature and amazon", names == ["amazon", "literature"], str(names))

    # ── Every shipped manifest is valid ───────────────────────
    for m in manifests:
        errs = m.get("_errors", [])
        check(f"{m.get('name')} manifest is valid", not errs, "; ".join(errs)[:200])

    # ── Fields the ticket names: name, version, description, tools, author
    for m in manifests:
        n = m.get("name")
        for field in ("name", "version", "description", "tools", "author"):
            check(f"{n} has {field}", field in m)

    # ── Semver ────────────────────────────────────────────────
    for m in manifests:
        v = m.get("version", "")
        parts = v.split(".")
        check(
            f"{m.get('name')} version is semver ({v})",
            len(parts) == 3 and all(p.isdigit() for p in parts),
            v,
        )

    # ── Manifest name must match the skill's own name ─────────
    # A mismatch means the registry advertises a skill the router cannot find.
    from skills.amazon import AmazonSkill
    from skills.literature import LiteratureSkill

    actual = {"literature": LiteratureSkill.name, "amazon": AmazonSkill.name}
    for m in manifests:
        n = m.get("name")
        check(f"{n} manifest name matches the class", actual.get(n) == n, f"class says {actual.get(n)}")

    # ── Entry points import ───────────────────────────────────
    import importlib

    for m in manifests:
        entry = (m.get("runtime") or {}).get("entryPoint", "")
        mod_name, _, cls_name = entry.partition(":")
        ok = False
        try:
            mod = importlib.import_module(mod_name)
            ok = hasattr(mod, cls_name)
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"        ({entry} -> {exc})")
        check(f"{m.get('name')} entryPoint resolves ({entry})", ok)

    # ── Tools ─────────────────────────────────────────────────
    tools = list_tools()
    check("flattens tools across skills", len(tools) == 8, f"got {len(tools)}")
    check("every tool is tagged with its skill", all(t.get("skill") for t in tools))

    tool_names = [t["name"] for t in tools]
    check("tool names are globally unique", len(tool_names) == len(set(tool_names)), str(tool_names))

    for t in tools:
        s = t.get("inputSchema", {})
        check(
            f"{t['name']} inputSchema is a valid object schema",
            s.get("type") == "object" and isinstance(s.get("properties"), dict),
            str(s)[:120],
        )
        for req in s.get("required", []):
            check(
                f"{t['name']} declares required field '{req}'",
                req in s.get("properties", {}),
            )

    # ── Lookup ────────────────────────────────────────────────
    check("get_manifest finds a known skill", get_manifest("literature") is not None)
    check("get_manifest returns None for unknown", get_manifest("nope") is None)

    # ── Schema file ───────────────────────────────────────────
    check("schema file exists", SCHEMA_PATH.exists(), str(SCHEMA_PATH))
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        check("schema is valid JSON", isinstance(schema, dict))
        check("schema declares required fields", "required" in schema)
    except json.JSONDecodeError as exc:
        check("schema is valid JSON", False, str(exc))

    # ── Validator rejects what it should ──────────────────────
    good = copy.deepcopy(next(m for m in manifests if m["name"] == "literature"))
    good.pop("_source", None)
    good.pop("_errors", None)
    check("validator accepts a good manifest", validate_manifest(good) == [])

    def mutated(**changes):
        d = copy.deepcopy(good)
        d.update(changes)
        return d

    cases = [
        ("bad semver", mutated(version="2.0"), "semver"),
        ("uppercase name", mutated(name="Literature"), "lowercase"),
        ("unsupported manifestVersion", mutated(manifestVersion="9.9"), "not supported"),
        ("empty tools", mutated(tools=[]), "empty"),
        ("short description", mutated(description="tiny"), "20-600"),
    ]
    for label, bad, expect in cases:
        errs = validate_manifest(bad)
        check(f"rejects {label}", any(expect in e for e in errs), f"got {errs}")

    # Duplicate tool names shadow each other at dispatch — must be caught.
    dup = copy.deepcopy(good)
    dup["tools"] = [dup["tools"][0], copy.deepcopy(dup["tools"][0])]
    check(
        "rejects duplicate tool names",
        any("duplicate" in e for e in validate_manifest(dup)),
        str(validate_manifest(dup)),
    )

    # A required field absent from properties is a schema that can never validate.
    orphan = copy.deepcopy(good)
    orphan["tools"][0]["inputSchema"]["required"] = ["nonexistent_field"]
    check(
        "rejects required field missing from properties",
        any("nonexistent_field" in e for e in validate_manifest(orphan)),
    )

    # ── Strict loading raises ─────────────────────────────────
    bad_path = MANIFEST_DIR / "_tmp_invalid.skill.json"
    try:
        bad_path.write_text(json.dumps({"name": "x"}), encoding="utf-8")
        raised = False
        try:
            load_manifest(bad_path, strict=True)
        except ManifestError:
            raised = True
        check("strict load raises on invalid manifest", raised)

        # Non-strict discovery must survive a broken file rather than blowing up
        # the registry endpoint.
        survived = discover_manifests(strict=False)
        broken = [m for m in survived if m.get("_errors")]
        check("non-strict discovery survives a broken manifest", len(broken) >= 1)
    finally:
        bad_path.unlink(missing_ok=True)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
