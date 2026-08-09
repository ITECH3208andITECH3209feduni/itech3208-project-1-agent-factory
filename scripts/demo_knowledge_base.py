# scripts/demo_knowledge_base.py
# ──────────────────────────────────────────────────────────────
# Demo script for Epic 14: ChromaDB Knowledge Base Engine
# Run: python scripts/demo_knowledge_base.py
# ──────────────────────────────────────────────────────────────

import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.knowledge_base.chroma_client import ChromaClientManager
from app.knowledge_base.ingestion import DocumentIngestor, DocumentInput
from app.knowledge_base.retrieval import QueryRetriever
from skills.knowledge_base import KnowledgeBaseSkill

console = Console()

SAMPLE_DOCUMENTS = [
    DocumentInput(
        title="Agent Architecture & Tool Design Guide",
        source="internal_docs",
        content=(
            "Agent Factory utilizes an orchestrator model where user requests are routed to specific "
            "skills based on intent matching and Claude AI reasoning. Skills subclass BaseSkill and return "
            "standardized SkillResult dataclasses containing raw results, human-readable summaries, and metadata. "
            "Session memory is backed by SQLite to preserve user conversation history across restarts."
        ),
        metadata={"category": "architecture", "author": "Engineering"}
    ),
    DocumentInput(
        title="Vector Database & ChromaDB Integration Policy",
        source="engineering_specs",
        content=(
            "ChromaDB provides local vector store capabilities for Agent Factory's RAG system. "
            "Text chunks are converted to vector embeddings and indexed using HNSW cosine space. "
            "Document chunking divides long text into 500-character segments with 50-character overlaps "
            "to ensure high-precision similarity searches during retrieval queries."
        ),
        metadata={"category": "knowledge_base", "author": "Saifur Rahman Bhuiyan"}
    ),
    DocumentInput(
        title="Amazon Product Scraper Fallback Strategy",
        source="runbooks",
        content=(
            "When direct Amazon web scraping encounters 503 or CAPTCHA errors, the system seamlessly falls "
            "back to DuckDuckGo search extraction and the RapidAPI Real-time Amazon Data endpoint. "
            "Product cards are normalized into standard schema formats with ASIN, title, rating, and price."
        ),
        metadata={"category": "scraping", "author": "Integrations Team"}
    )
]


def run_demo():
    console.print(Panel.fit("[bold cyan]Agent Factory - Knowledge Base Engine (ChromaDB) Demo[/bold cyan]"))

    # 1. Setup & Health Check
    client_mgr = ChromaClientManager(in_memory=True)  # Use in-memory for quick demo execution
    health = client_mgr.health_check()
    console.print(f"[bold green][OK] ChromaDB Status:[/bold green] {health}")

    # 2. Document Ingestion
    console.print("\n[bold yellow]1. Ingesting Sample Knowledge Base Documents...[/bold yellow]")
    ingestor = DocumentIngestor(client_manager=client_mgr)
    
    ingest_table = Table(title="Ingested Documents", show_header=True, header_style="bold magenta")
    ingest_table.add_column("Doc ID", style="cyan")
    ingest_table.add_column("Title", style="white")
    ingest_table.add_column("Chunks", style="green")
    ingest_table.add_column("Duration", style="yellow")

    for doc in SAMPLE_DOCUMENTS:
        res = ingestor.ingest_document(doc)
        ingest_table.add_row(res.document_id, res.title, str(res.chunks_count), f"{res.duration_sec}s")

    console.print(ingest_table)

    # 3. Vector Similarity Search Queries
    retriever = QueryRetriever(client_manager=client_mgr)
    queries = [
        "How does vector document chunking work in ChromaDB?",
        "What happens when Amazon scraping gets blocked?",
        "How are session conversations saved across restarts?"
    ]

    console.print("\n[bold yellow]2. Executing Vector Search Queries...[/bold yellow]")
    for q in queries:
        console.print(f"\n[bold underline]Query:[/bold underline] '{q}'")
        search_res = retriever.search(q, n_results=2)

        results_table = Table(show_header=True, header_style="bold blue")
        results_table.add_column("Score", style="green")
        results_table.add_column("Title", style="cyan")
        results_table.add_column("Matched Snippet", style="dim white")

        for item in search_res.results:
            results_table.add_row(
                f"{item.score:.2f}",
                item.title,
                item.text[:120] + "..." if len(item.text) > 120 else item.text
            )
        console.print(results_table)

    # 4. KnowledgeBaseSkill Test
    console.print("\n[bold yellow]3. Testing KnowledgeBaseSkill Interface...[/bold yellow]")
    kb_skill = KnowledgeBaseSkill(retriever=retriever)
    skill_res = kb_skill("Tell me about ChromaDB HNSW cosine indexing")
    console.print(f"[bold green]Skill Result Summary:[/bold green] {skill_res.summary}")
    console.print(f"[bold green]Skill Execution Duration:[/bold green] {skill_res.duration_sec:.3f}s")


if __name__ == "__main__":
    run_demo()
