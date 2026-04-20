# agent/formatter.py
# ──────────────────────────────────────────────────────────────
# Formats SkillResult into readable Markdown or JSON output (PROJ-23)
# ──────────────────────────────────────────────────────────────

import json
import os
from datetime import datetime
from skills.base_skill import SkillResult
from config.settings import OUTPUT_DIR


class Formatter:
    def __init__(self, output_format: str = "markdown"):
        self.format = output_format  # "markdown" | "json"
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    def render(self, result: SkillResult) -> str:
        """Return formatted string for terminal display."""
        if self.format == "json":
            return json.dumps(result.to_dict(), indent=2)
        return self._render_markdown(result)

    def save(self, result: SkillResult) -> str:
        """Save output to file, returns path."""
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext      = "md" if self.format == "markdown" else "json"
        filename = f"{OUTPUT_DIR}/{result.skill_name}_{ts}.{ext}"
        content  = self.render(result)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return filename

    # ── Markdown renderers ─────────────────────────────────────
    def _render_markdown(self, result: SkillResult) -> str:
        if result.skill_name == "literature":
            return self._render_literature(result)
        elif result.skill_name == "amazon":
            return self._render_amazon(result)
        return self._render_generic(result)

    def _render_literature(self, result: SkillResult) -> str:
        ts    = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# 📚 Literature Research Report",
            f"**Query:** {result.query}  |  **Generated:** {ts}  |  **Duration:** {result.duration_sec:.2f}s",
            f"\n> {result.summary}",
            "\n---\n",
        ]
        if not result.success or not result.results:
            lines.append(f"❌ **No results found.**  \n{result.error}")
            return "\n".join(lines)

        for i, paper in enumerate(result.results, 1):
            lines.append(f"## {i}. {paper.get('title', 'Untitled')}")
            lines.append(f"**Authors:** {paper.get('authors', 'Unknown')}  |  **Year:** {paper.get('year', 'N/A')}  |  **Source:** {paper.get('source', '')}")
            if paper.get("citations"):
                lines.append(f"**Citations:** {paper['citations']}")
            if paper.get("abstract"):
                lines.append(f"\n{paper['abstract']}...")
            if paper.get("link"):
                lines.append(f"\n🔗 [Read paper]({paper['link']})")
            lines.append("\n---")

        if result.error:
            lines.append(f"\n⚠️ **Partial errors:** {result.error}")
        return "\n".join(lines)

    def _render_amazon(self, result: SkillResult) -> str:
        ts    = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# 🛒 Amazon Product Research Report",
            f"**Query:** {result.query}  |  **Generated:** {ts}  |  **Duration:** {result.duration_sec:.2f}s",
            f"\n> {result.summary}",
            "\n---\n",
        ]
        if not result.success or not result.results:
            lines.append(f"❌ **No products found.**  \n{result.error}")
            return "\n".join(lines)

        for i, product in enumerate(result.results, 1):
            prime_badge = " 🟦 Prime" if product.get("prime") else ""
            lines.append(f"## {i}. {product.get('title', 'Unknown Product')}{prime_badge}")
            lines.append(
                f"**Price:** {product.get('price', 'N/A')}  |  "
                f"**Rating:** {product.get('rating', 'N/A')}  |  "
                f"**Reviews:** {product.get('reviews', 'N/A')}"
            )
            if product.get("link"):
                lines.append(f"\n🔗 [View on Amazon]({product['link']})")
            lines.append("\n---")

        search_url = result.metadata.get("search_url", "")
        if search_url:
            lines.append(f"\n🔍 [See all results on Amazon]({search_url})")
        return "\n".join(lines)

    def _render_generic(self, result: SkillResult) -> str:
        lines = [
            f"# Agent Result — {result.skill_name.title()}",
            f"**Query:** {result.query}",
            f"**Success:** {'✅' if result.success else '❌'}",
            f"**Summary:** {result.summary}",
            "\n---\n",
        ]
        for i, item in enumerate(result.results, 1):
            lines.append(f"{i}. {json.dumps(item, indent=2)}")
        return "\n".join(lines)
