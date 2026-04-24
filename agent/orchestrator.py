# agent/orchestrator.py
# ──────────────────────────────────────────────────────────────
# Main agent orchestrator — decides which skill to call (PROJ-20)
# Uses Claude for intent classification + result summarisation
# ──────────────────────────────────────────────────────────────

import anthropic

from skills.base_skill import BaseSkill, SkillResult
from skills.literature import LiteratureSkill
from skills.amazon     import AmazonSkill
from agent.memory      import Memory
from agent.formatter   import Formatter
from config.settings   import ANTHROPIC_API_KEY, CLAUDE_MODEL


SYSTEM_PROMPT = """You are a 24/7 Research AI Assistant that helps with two specialised tasks:

1. LITERATURE RESEARCH — finding academic papers, studies, and scientific articles
2. AMAZON PRODUCT RESEARCH — finding, comparing, and recommending products on Amazon

Your job is to:
- Understand what the user wants
- Route to the correct skill
- Summarise results clearly and helpfully

Always be concise, factual, and helpful. When uncertain, ask a short clarifying question."""


ROUTING_PROMPT = """Given the user query below, decide which skill to use.

Available skills:
- "literature" — for academic papers, research, studies, journals, science
- "amazon"     — for products, shopping, buying, prices, reviews, recommendations
- "clarify"    — if the query is too ambiguous to route (return a short question to ask the user)

Recent conversation context:
{context}

User query: "{query}"

Respond with ONLY ONE of:
SKILL: literature
SKILL: amazon
CLARIFY: <your clarifying question>"""


# Module-level skill registry (PROJ-32 spec). Mirrors the instance-level
# self.skills in Orchestrator.__init__ — both point to the same skill classes.
# Kept for spec compatibility and external imports.
SKILLS = {
    "literature": LiteratureSkill(),
    "amazon":     AmazonSkill(),
}


class Orchestrator:
    def __init__(self, output_format: str = "markdown"):
        self.client    = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.memory    = Memory()
        self.formatter = Formatter(output_format=output_format)
        self.skills: dict[str, BaseSkill] = {
            "literature": LiteratureSkill(),
            "amazon":     AmazonSkill(),
        }

    # ── Main entry point ───────────────────────────────────────
    def run(self, query: str) -> tuple[str, SkillResult | None]:
        """
        Process a user query end-to-end.
        Returns (rendered_output: str, result: SkillResult | None)
        """
        # 1. Route to the right skill
        skill_name = self._route(query)

        # 2. Handle clarification request
        if skill_name.startswith("CLARIFY:"):
            clarify_msg = skill_name.replace("CLARIFY:", "").strip()
            return clarify_msg, None

        # 3. Run the skill
        skill  = self.skills[skill_name]
        result = skill(query)

        # 4. Let Claude summarise the findings
        if result.success and result.results:
            result.summary = self._summarise(query, result)

        # 5. Persist to memory (PROJ-33: use spec method save_context)
        if result.success:
            self.memory.save_context(query, skill_name, result.summary)

        # 6. Format and return
        rendered = self.formatter.render(result)
        return rendered, result

    def run_and_save(self, query: str) -> tuple[str, str, SkillResult | None]:
        """
        Same as run() but also saves the output to a file.
        Returns (rendered_output, saved_filepath, result)
        """
        rendered, result = self.run(query)
        if result:
            path = self.formatter.save(result)
            return rendered, path, result
        return rendered, "", None

    # ── Intent routing ─────────────────────────────────────────
    def _route(self, query: str) -> str:
        """Ask Claude to classify the query intent."""
        context = self.memory.get_context_string(last_n=3)
        prompt  = ROUTING_PROMPT.format(context=context, query=query)

        # Quick keyword pre-check (saves an API call for obvious queries)
        quick_route = self._quick_route(query)
        if quick_route:
            return quick_route

        message = self.client.messages.create(
            model      = CLAUDE_MODEL,
            max_tokens = 60,
            messages   = [{"role": "user", "content": prompt}],
        )
        response = message.content[0].text.strip()

        if "SKILL: literature" in response:
            return "literature"
        elif "SKILL: amazon" in response:
            return "amazon"
        elif "CLARIFY:" in response:
            return response  # pass the clarification back
        else:
            # Default fallback
            return "literature"

    def _quick_route(self, query: str) -> str | None:
        """Fast keyword-based routing — no API call needed."""
        q = query.lower()
        amazon_keywords    = {"buy", "price", "amazon", "product", "shop", "deal", "cheap", "best", "review"}
        literature_keywords= {"paper", "research", "study", "journal", "arxiv", "pubmed", "author", "cite"}

        amazon_hits    = sum(1 for k in amazon_keywords    if k in q)
        literature_hits= sum(1 for k in literature_keywords if k in q)

        if amazon_hits > literature_hits and amazon_hits >= 1:
            return "amazon"
        if literature_hits > amazon_hits and literature_hits >= 1:
            return "literature"
        return None  # fall through to Claude

    # ── Result summarisation ───────────────────────────────────
    def _summarise(self, query: str, result: SkillResult) -> str:
        """Use Claude to write a human-friendly summary of the results."""
        if result.skill_name == "literature":
            items = "\n".join(
                f"- {r['title']} ({r.get('year','?')}) by {r.get('authors','?')}"
                for r in result.results[:5]
            )
            prompt = (
                f"The user asked: '{query}'\n\n"
                f"Here are the top papers found:\n{items}\n\n"
                "Write a 2-3 sentence summary highlighting the most relevant findings and what the user should look at first."
            )
        else:  # amazon
            items = "\n".join(
                f"- {r['title']} | {r.get('price','?')} | Rating: {r.get('rating','?')}"
                for r in result.results[:5]
            )
            prompt = (
                f"The user asked: '{query}'\n\n"
                f"Here are the top products found:\n{items}\n\n"
                "Write a 2-3 sentence summary with a clear recommendation on which product to consider first and why."
            )

        try:
            message = self.client.messages.create(
                model      = CLAUDE_MODEL,
                max_tokens = 200,
                system     = SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception:
            return result.summary  # fall back to the auto-generated summary