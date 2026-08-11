# skills/general_qa.py
# ──────────────────────────────────────────────────────────────
# General Q&A sub-agent (PROJ-249..253)
# Lightweight direct Claude Haiku call. Acts as the fallback
# when no specialised skill matches the user's intent.
# ──────────────────────────────────────────────────────────────

import os

import anthropic

from skills.base_skill import BaseSkill, SkillResult
from config.settings import ANTHROPIC_API_KEY

HAIKU_MODEL = os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")

QA_SYSTEM_PROMPT = """You are the general Q&A assistant inside a multi-agent system.

You handle questions that don't fit the specialised skills (literature search,
Amazon product research, academic integrity, seller tools).

Rules:
- Answer directly and concisely.
- Format your answer in markdown.
- Use headings and bullet points only when they genuinely aid clarity.
- If you don't know something, say so plainly rather than guessing."""


class GeneralQASkill(BaseSkill):
    name = "general"
    description = "General questions that don't match a specialised skill. Fallback handler."
    triggers = ["what", "how", "why", "explain", "who", "when", "define"]

    def __init__(self, model: str = HAIKU_MODEL, max_tokens: int = 1024):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = model
        self.max_tokens = max_tokens

    def run(self, query: str) -> SkillResult:
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=QA_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": query}],
            )
            answer = message.content[0].text.strip()
        except Exception as exc:
            return SkillResult(
                skill_name=self.name,
                query=query,
                success=False,
                error=f"Claude call failed: {exc}",
            )

        return SkillResult(
            skill_name=self.name,
            query=query,
            success=True,
            results=[{"answer": answer, "format": "markdown"}],
            summary=answer,
            metadata={
                "model": self.model,
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            },
        )