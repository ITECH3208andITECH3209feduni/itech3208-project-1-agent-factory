"""
app.openclaw.skills_registry — Registry of available OpenClaw skills.

Skills are stored as a dict keyed by name. Each entry contains:
  - handler     : callable that accepts a query string and returns a result
  - description : human-readable description of what the skill does
  - timeout     : seconds before the skill call is considered timed out
"""

from skills.amazon import AmazonSkill
from skills.literature import LiteratureSkill

# Instantiate skill handlers once at import time
_amazon_skill = AmazonSkill()
_literature_skill = LiteratureSkill()

SKILLS: dict[str, dict] = {
    "amazon": {
        "handler": _amazon_skill.run,
        "description": (
            "Search Amazon for products, compare prices, read ratings and reviews. "
            "Use for buying recommendations, price comparisons, and product research."
        ),
        "timeout": 60,
    },
    "literature": {
        "handler": _literature_skill.run,
        "description": (
            "Search academic papers and scientific literature via arXiv, "
            "Semantic Scholar, and PubMed. Use for research queries, citations, "
            "and paper synthesis."
        ),
        "timeout": 30,
    },
}


def register_skill(name: str, handler: callable, description: str, timeout: int = 30) -> None:
    """Add a new skill to the registry."""
    SKILLS[name] = {
        "handler": handler,
        "description": description,
        "timeout": timeout,
    }


def get_skill(name: str) -> dict:
    """Return the skill entry for name. Raises KeyError if not found."""
    if name not in SKILLS:
        available = ", ".join(SKILLS.keys())
        raise KeyError(f"Skill '{name}' not found. Available skills: {available}")
    return SKILLS[name]


def list_skills() -> list[str]:
    """Return the names of all registered skills."""
    return list(SKILLS.keys())
