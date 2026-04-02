# skills/base_skill.py
# ──────────────────────────────────────────────────────────────
# Abstract base class that every skill must inherit.
# Enforces a consistent interface across all skills.
# ──────────────────────────────────────────────────────────────

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import time


@dataclass
class SkillResult:
    """Standardised return type for every skill."""
    skill_name:  str
    query:       str
    success:     bool
    results:     list[dict]          = field(default_factory=list)
    summary:     str                 = ""
    error:       str                 = ""
    metadata:    dict[str, Any]      = field(default_factory=dict)
    duration_sec: float              = 0.0

    def to_dict(self) -> dict:
        return {
            "skill":    self.skill_name,
            "query":    self.query,
            "success":  self.success,
            "results":  self.results,
            "summary":  self.summary,
            "error":    self.error,
            "metadata": self.metadata,
            "duration": f"{self.duration_sec:.2f}s",
        }


class BaseSkill(ABC):
    """
    All skills inherit from this class.

    Required:
        name        (str)  — unique skill identifier
        description (str)  — shown to the orchestrator for routing
        triggers    (list) — keywords that hint at this skill

    Required methods:
        run(query: str) -> SkillResult
    """

    name:        str = "base"
    description: str = "Base skill — do not use directly."
    triggers:    list[str] = []

    def __call__(self, query: str) -> SkillResult:
        start = time.time()
        try:
            result = self.run(query)
        except Exception as exc:
            result = SkillResult(
                skill_name=self.name,
                query=query,
                success=False,
                error=str(exc),
            )
        result.duration_sec = time.time() - start
        return result

    @abstractmethod
    def run(self, query: str) -> SkillResult:
        """Execute the skill and return a SkillResult."""
        ...

    def __repr__(self) -> str:
        return f"<Skill: {self.name}>"
