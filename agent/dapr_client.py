# agent/dapr_client.py
import os
import requests
from skills.base_skill import SkillResult

DAPR_PORT = os.getenv("DAPR_HTTP_PORT", "3500")
DAPR_BASE = f"http://localhost:{DAPR_PORT}/v1.0/invoke"

APP_IDS = {
    "literature": "literature-agent",
    "amazon":     "amazon-agent",
    "integrity":  "integrity-agent",
    "seller":     "seller-agent",
}


class DaprUnavailable(Exception):
    pass


def result_from_dict(d: dict) -> SkillResult:
    """Rebuild a SkillResult from to_dict() output."""
    duration = d.get("duration", 0.0)
    if isinstance(duration, str):
        duration = float(duration.rstrip("s") or 0)
    return SkillResult(
        skill_name   = d.get("skill") or d.get("skill_name", ""),
        query        = d.get("query", ""),
        success      = d.get("success", False),
        results      = d.get("results", []),
        summary      = d.get("summary", ""),
        error        = d.get("error", ""),
        metadata     = d.get("metadata", {}),
        duration_sec = duration,
    )


def invoke_skill(skill_name: str, query: str, timeout: int = 90) -> SkillResult:
    app_id = APP_IDS.get(skill_name)
    if not app_id:
        raise DaprUnavailable(f"no app-id mapped for '{skill_name}'")
    try:
        resp = requests.post(
            f"{DAPR_BASE}/{app_id}/method/invoke",
            json={"query": query},
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise DaprUnavailable(str(exc)) from exc
    return result_from_dict(resp.json())