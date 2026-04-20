#!/usr/bin/env python3
# main.py
# ──────────────────────────────────────────────────────────────
# Agent Factory — Entry Point
# Usage:
#   python main.py                          # interactive mode
#   python main.py -q "RAG architecture"   # single query mode
#   python main.py -q "best laptop $1000" --save   # save output
#   python main.py --history               # show recent queries
#   python main.py --clear-memory          # reset memory
# ──────────────────────────────────────────────────────────────

import argparse
import os
import sys

# ── Rich for pretty terminal output (optional but recommended) ─
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.text import Text
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    console = None

from agent.orchestrator import Orchestrator


BANNER = """
╔══════════════════════════════════════════════════════════════╗
║          🤖  AGENT FACTORY  —  RESEARCH AI ASSISTANT        ║
║          Literature Search  |  Amazon Product Research       ║
║          Type 'quit' or 'exit' to stop   |  'help' for tips ║
╚══════════════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
📖 EXAMPLE QUERIES
──────────────────────────────────────────────
Literature:
  • "Find papers on transformer architecture"
  • "Research on CRISPR gene editing 2024"
  • "Meta-analysis of intermittent fasting"

Amazon:
  • "Best wireless earbuds under $50"
  • "Top rated standing desk 2024"
  • "Lightweight laptop for students"

Commands:
  • history   — show your last 5 queries
  • save      — save the last result to file
  • clear     — clear session memory
  • quit/exit — exit the assistant
──────────────────────────────────────────────
"""


def print_output(text: str):
    if RICH:
        try:
            console.print(Markdown(text))
        except Exception:
            print(text)
    else:
        print(text)


def print_info(text: str, style: str = "bold cyan"):
    if RICH:
        console.print(text, style=style)
    else:
        print(text)


def run_interactive(agent: Orchestrator):
    """Interactive REPL loop."""
    print(BANNER)
    print_info("Ready. Ask me about research papers or Amazon products.\n")

    last_result = None

    while True:
        try:
            query = input("🔍 You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print_info("\n\nGoodbye! 👋", "bold green")
            break

        if not query:
            continue

        q_lower = query.lower()

        # ── Built-in commands ──────────────────────────────────
        if q_lower in ("quit", "exit", "bye"):
            print_info("\nGoodbye! 👋", "bold green")
            break

        if q_lower == "help":
            print(HELP_TEXT)
            continue

        if q_lower == "history":
            history = agent.memory.get_history(5)
            if not history:
                print_info("No queries yet.", "yellow")
            for h in history:
                print_info(f"  [{h['skill']}] {h['query'][:60]}...", "dim")
            continue

        if q_lower == "clear":
            agent.memory.clear()
            print_info("Memory cleared.", "yellow")
            continue

        if q_lower == "save" and last_result:
            path = agent.formatter.save(last_result)
            print_info(f"✅ Saved to: {path}", "bold green")
            continue

        if q_lower == "stats":
            stats = agent.memory.stats()
            print_info(f"Total queries: {stats['total_queries']} | Session started: {stats['session_started'][:19]}")
            continue

        # ── Run the agent ──────────────────────────────────────
        print_info("\n⏳ Researching...\n", "dim")
        try:
            rendered, result = agent.run(query)
            last_result = result
            print_output(rendered)
            if result:
                print_info(f"\n⏱  Done in {result.duration_sec:.2f}s\n", "dim")
        except Exception as e:
            print_info(f"\n❌ Error: {e}", "bold red")


def run_single(agent: Orchestrator, query: str, save: bool = False):
    """Single query mode (non-interactive)."""
    print_info(f"\n⏳ Processing: {query}\n", "dim")
    try:
        if save:
            rendered, path, result = agent.run_and_save(query)
            print_output(rendered)
            if path:
                print_info(f"\n✅ Saved to: {path}", "bold green")
        else:
            rendered, result = agent.run(query)
            print_output(rendered)
    except Exception as e:
        print_info(f"❌ Error: {e}", "bold red")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Agent Factory — 24/7 Research AI Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP_TEXT,
    )
    parser.add_argument("-q", "--query",   type=str, help="Run a single query and exit")
    parser.add_argument("--save",          action="store_true", help="Save output to file")
    parser.add_argument("--format",        choices=["markdown", "json"], default="markdown")
    parser.add_argument("--history",       action="store_true", help="Show query history and exit")
    parser.add_argument("--clear-memory",  action="store_true", help="Clear memory and exit")
    args = parser.parse_args()

    # Check API key
    if os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE") == "YOUR_API_KEY_HERE":
        from config.settings import ANTHROPIC_API_KEY
        if ANTHROPIC_API_KEY == "YOUR_API_KEY_HERE":
            print("⚠️  Set your API key first:")
            print("   export ANTHROPIC_API_KEY=your_key_here")
            print("   or edit config/settings.py")
            sys.exit(1)

    agent = Orchestrator(output_format=args.format)

    if args.clear_memory:
        agent.memory.clear()
        print("Memory cleared.")
        return

    if args.history:
        history = agent.memory.get_history(10)
        for h in history:
            print(f"[{h['timestamp'][:16]}] ({h['skill']}) {h['query']}")
        return

    if args.query:
        run_single(agent, args.query, save=args.save)
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
