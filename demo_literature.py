#!/usr/bin/env python3
"""
demo_literature.py — Sprint 2 end-to-end demo of the Literature Research pipeline.

Runs three queries that exercise every major mode:
  1. Multi-paper synthesis   (arXiv + Semantic Scholar → Claude Haiku synthesis)
  2. Research gap analysis   (same sources → Claude Haiku gap finder)
  3. Forward citation lookup (Semantic Scholar citations endpoint)

Usage:
  python demo_literature.py
  python demo_literature.py --topic "large language models"
"""

import argparse
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.rule import Rule
    RICH = True
    console = Console()
except ImportError:
    RICH = False

from skills.literature import LiteratureSkill
from components.literature_cards import PaperCard


def section(title: str):
    if RICH:
        console.print(Rule(f"[bold cyan]{title}[/bold cyan]"))
    else:
        print(f"\n{'='*60}\n{title}\n{'='*60}")


def show(text: str):
    if RICH:
        try:
            console.print(Markdown(text))
        except Exception:
            print(text)
    else:
        print(text)


def show_cards(results: list[dict], limit: int = 5):
    cards = []
    for raw in results[:limit]:
        try:
            cards.append(PaperCard.from_skill_result(raw))
        except Exception:
            pass

    if RICH:
        for c in cards:
            console.print(
                f"  [bold]{c.title}[/bold] [dim]({c.year})[/dim]\n"
                f"  [italic]{c.authors}[/italic]  |  {c.citations:,} citations  |  [link={c.url}]{c.source}[/link]\n"
                f"  {c.truncate_abstract(180)}\n"
            )
    else:
        for c in cards:
            print(f"  [{c.source}] {c.title} ({c.year})")
            print(f"  Authors: {c.authors}")
            print(f"  Citations: {c.citations}")
            print(f"  {c.truncate_abstract(180)}")
            print()


def run_demo(topic: str):
    skill = LiteratureSkill()

    # ── 1. Multi-paper synthesis ───────────────────────────────
    section(f"1 / 3  Multi-Paper Synthesis — '{topic}'")
    synthesis_query = f"synthesise papers on {topic}"
    result = skill(synthesis_query)

    print(f"\nFetched {len(result.results)} papers  |  "
          f"Sources: {', '.join(result.metadata.get('sources_queried', []))}  |  "
          f"Duration: {result.duration_sec:.1f}s\n")

    show_cards(result.results)

    if result.metadata.get("synthesis_done"):
        synthesis_section = [
            line for line in result.summary.split("\n")
            if "Cross-Paper Synthesis" in line or result.summary.find("##") == -1
        ]
        # Show everything after the paper-list summary
        show(result.summary)
    else:
        show(result.summary)
        show("*(Set ANTHROPIC_API_KEY to enable Claude Haiku synthesis)*")

    # ── 2. Research gap analysis ───────────────────────────────
    section(f"2 / 3  Research Gap Analysis — '{topic}'")
    gap_query = f"research gaps in {topic}"
    result2 = skill(gap_query)

    print(f"\nFetched {len(result2.results)} papers  |  "
          f"Duration: {result2.duration_sec:.1f}s\n")

    if result2.metadata.get("gap_analysis_done"):
        show(result2.summary)
    else:
        show(result2.summary)
        show("*(Set ANTHROPIC_API_KEY to enable Claude Haiku gap analysis)*")

    # ── 3. Forward citation lookup ─────────────────────────────
    section("3 / 3  Forward Citation Lookup — 'Attention is All You Need'")
    # Use the arXiv ID directly to avoid an extra search round-trip
    citation_query = "citations for ARXIV:1706.03762"
    result3 = skill(citation_query)

    print(f"\nFound {result3.metadata.get('citing_count', 0)} citing papers  |  "
          f"Duration: {result3.duration_sec:.1f}s\n")

    show_cards(result3.results, limit=5)
    show(result3.summary)

    # ── Summary ────────────────────────────────────────────────
    section("Demo Complete")
    show(
        f"| Mode | Papers | Success |\n"
        f"|---|---|---|\n"
        f"| Synthesis | {len(result.results)} | {'yes' if result.success else 'no'} |\n"
        f"| Gap analysis | {len(result2.results)} | {'yes' if result2.success else 'no'} |\n"
        f"| Citation lookup | {result3.metadata.get('citing_count', 0)} citing papers | {'yes' if result3.success else 'no'} |"
    )


def main():
    parser = argparse.ArgumentParser(description="Literature Research Agent — Sprint 2 Demo")
    parser.add_argument("--topic", default="retrieval-augmented generation",
                        help="Research topic for synthesis and gap queries (default: retrieval-augmented generation)")
    args = parser.parse_args()

    if os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE") == "YOUR_API_KEY_HERE":
        print("Warning: ANTHROPIC_API_KEY not set — Claude synthesis/gap modes will be skipped.\n"
              "Set it with:  $env:ANTHROPIC_API_KEY='sk-ant-...'  (PowerShell)\n")

    run_demo(args.topic)


if __name__ == "__main__":
    main()
