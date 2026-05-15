"""
app.agent — OpenClaw-integrated agent entry point.

Routes queries through OpenClaw SDK first. Falls back to direct skill
execution if OpenClaw is unavailable or OPENCLAW_ENABLED=false.
"""

import logging
import os

from app.openclaw.client import OpenClawWrapper
from app.openclaw.router import route_query, classify
from app.openclaw.skills_registry import get_skill
from config.settings import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

OPENCLAW_ENABLED = os.environ.get("OPENCLAW_ENABLED", "true").lower() != "false"


def run_query(query: str, wrapper: OpenClawWrapper | None = None) -> dict:
    """
    Process a query through OpenClaw (primary) or direct skill (fallback).

    Returns a dict with at least a 'result' key.
    Logs whether 'openclaw' or 'fallback' path was taken.
    """
    if OPENCLAW_ENABLED and wrapper is not None:
        try:
            result = route_query(query, wrapper)
            logger.info("path=openclaw skill=%s query=%r", result.get("skill"), query[:60])
            return result
        except (ConnectionError, KeyError, Exception) as e:
            logger.warning("OpenClaw failed (%s), switching to fallback", e)

    # Fallback: call skill handler directly from registry
    skill_name = classify(query)
    try:
        skill_entry = get_skill(skill_name)
        handler = skill_entry["handler"]
        skill_result = handler(query)
        logger.info("path=fallback skill=%s query=%r", skill_name, query[:60])
        # Normalise to dict so callers get a consistent return type
        if hasattr(skill_result, "__dict__"):
            return {"result": skill_result.summary, "skill": skill_name, "status": "ok", "raw": skill_result}
        return {"result": str(skill_result), "skill": skill_name, "status": "ok"}
    except Exception as e:
        logger.error("Fallback also failed for skill=%s: %s", skill_name, e)
        return {"result": None, "skill": skill_name, "status": "error", "error": str(e)}
