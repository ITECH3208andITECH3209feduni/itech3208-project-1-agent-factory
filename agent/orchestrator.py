# agent/orchestrator.py
# ──────────────────────────────────────────────────────────────
# Main agent orchestrator — decides which skill to call (PROJ-20)
# Uses Claude for intent classification + result summarisation
# PROJ-254..258: skills are now invoked via Dapr service invocation,
# with an in-process fallback when Dapr is unavailable.
# PROJ-249..253: general Q&A sub-agent added as the fallback route.
# ──────────────────────────────────────────────────────────────

import os

import anthropic

from skills.base_skill import BaseSkill, SkillResult
from skills.literature         import LiteratureSkill
from skills.amazon             import AmazonSkill
from skills.academic_integrity import AcademicIntegritySkill
from skills.amazon_seller      import AmazonSellerSkill
from skills.general_qa         import GeneralQASkill
from agent.memory      import SessionMemory
from agent.formatter   import Formatter
from agent.dapr_client import invoke_skill, DaprUnavailable
from config.settings   import ANTHROPIC_API_KEY, CLAUDE_MODEL


SYSTEM_PROMPT = """You are a 24/7 AI Assistant that helps with four specialised tasks:

1. LITERATURE RESEARCH — finding academic papers, studies, and scientific articles
2. AMAZON PRODUCT RESEARCH — finding, comparing, and recommending products on Amazon
3. ACADEMIC INTEGRITY — detecting AI-generated text, scanning for plagiarism, generating integrity reports
4. AMAZON SELLER TOOLS — Alibaba supplier finder, PPC campaign builder, product progress analysis, profit optimiser

Anything outside these four is handled by the general Q&A assistant.

Your job is to:
- Understand what the user wants
- Route to the correct skill
- Summarise results clearly and helpfully

Always be concise, factual, and helpful. When uncertain, ask a short clarifying question."""


ROUTING_PROMPT = """Given the user query below, decide which skill to use.

Available skills:
- "literature"  — academic papers, research, studies, journals, science, arxiv, pubmed
- "amazon"      — products, shopping, buying, prices, reviews, recommendations
- "integrity"   — detect AI-written text, plagiarism check, academic integrity report
- "seller"      — alibaba suppliers, PPC campaign, product progress, profit optimiser, margin analysis
- "general"     — any other question that does not fit the skills above
- "clarify"     — if the query is too ambiguous to route

Recent conversation context:
{context}

User query: "{query}"

Respond with ONLY ONE of:
SKILL: literature
SKILL: amazon
SKILL: integrity
SKILL: seller
SKILL: general
CLARIFY: <your clarifying question>"""


# Module-level skill registry (PROJ-32 spec).
SKILLS = {
    "literature": LiteratureSkill(),
    "amazon":     AmazonSkill(),
    "integrity":  AcademicIntegritySkill(),
    "seller":     AmazonSellerSkill(),
    "general":    GeneralQASkill(),
}


class Orchestrator:
    def __init__(self, output_format: str = "markdown"):
        self.client    = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.memory    = SessionMemory()
        self.formatter = Formatter(output_format=output_format)
        self.skills: dict[str, BaseSkill] = {
            "literature": LiteratureSkill(),
            "amazon":     AmazonSkill(),
            "integrity":  AcademicIntegritySkill(),
            "seller":     AmazonSellerSkill(),
            "general":    GeneralQASkill(),
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

        # 3. Run the skill (via Dapr when enabled, else in-process)
        result = self._run_skill(skill_name, query)

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

    # ── Skill execution ────────────────────────────────────────
    def _run_skill(self, skill_name: str, query: str) -> SkillResult:
        """
        Execute a skill.

        When USE_DAPR=true the call goes out over the Dapr sidecar to the
        matching sub-agent service. If the sidecar or the service is not
        reachable we fall back to running the skill in-process, so the app
        keeps working even with Dapr down.
        """
        if os.getenv("USE_DAPR", "false").lower() == "true":
            try:
                return invoke_skill(skill_name, query)
            except DaprUnavailable as exc:
                print(f"[dapr] unavailable, running in-process: {exc}")
        return self.skills[skill_name](query)

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
        elif "SKILL: integrity" in response:
            return "integrity"
        elif "SKILL: seller" in response:
            return "seller"
        elif "SKILL: general" in response:
            return "general"
        elif "CLARIFY:" in response:
            return response  # pass the clarification back
        else:
            # Unrecognised intent — hand off to the general Q&A sub-agent
            return "general"

    def _quick_route(self, query: str) -> str | None:
        """Fast keyword-based routing — no API call needed."""
        q = query.lower()
        amazon_keywords     = {"buy", "price", "amazon", "product", "shop", "deal", "cheap", "best", "review"}
        literature_keywords = {"paper", "research", "study", "journal", "arxiv", "pubmed", "author", "cite"}
        integrity_keywords  = {"detect ai", "ai written", "plagiarism", "academic integrity",
                               "ai detection", "gpt detection", "check if ai", "integrity report"}
        seller_keywords     = {"alibaba", "supplier", "ppc", "campaign", "sponsored", "profit",
                               "margin", "acos", "bsr trend", "wholesale", "manufacturer"}

        integrity_hits  = sum(1 for k in integrity_keywords  if k in q)
        seller_hits     = sum(1 for k in seller_keywords     if k in q)
        amazon_hits     = sum(1 for k in amazon_keywords     if k in q)
        literature_hits = sum(1 for k in literature_keywords if k in q)

        if integrity_hits >= 1:
            return "integrity"
        if seller_hits >= 1:
            return "seller"
        if amazon_hits > literature_hits and amazon_hits >= 1:
            return "amazon"
        if literature_hits > amazon_hits and literature_hits >= 1:
            return "literature"
        return None  # fall through to Claude

    # ── Result summarisation ───────────────────────────────────
    def _summarise(self, query: str, result: SkillResult) -> str:
        """Use Claude to write a human-friendly summary of the results."""
        # General Q&A already returns a finished markdown answer — don't re-summarise.
        if result.skill_name == "general":
            return result.summary

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
        elif result.skill_name == "integrity":
            meta = result.metadata
            prompt = (
                f"The user asked: '{query}'\n\n"
                f"Academic integrity analysis results:\n"
                f"- AI probability: {meta.get('ai_probability', 0)*100:.0f}%\n"
                f"- Classification: {meta.get('classification', 'Unknown')}\n"
                f"- Plagiarism similarity: {meta.get('similarity_score', 0)*100:.0f}%\n"
                f"- Risk level: {meta.get('risk_level', 'low')}\n\n"
                "Write a 2-3 sentence summary of the findings and what action should be taken."
            )
        elif result.skill_name == "amazon_seller":
            mode = result.metadata.get("mode", "unknown")
            prompt = (
                f"The user asked: '{query}'\n\n"
                f"Amazon seller tool result (mode: {mode}):\n"
                f"{result.summary[:400] if result.summary else 'No summary available.'}\n\n"
                "Write a 2-3 sentence actionable summary for the seller."
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