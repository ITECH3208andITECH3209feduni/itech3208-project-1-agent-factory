# skills/knowledge_base.py
# ──────────────────────────────────────────────────────────────
# Knowledge Base RAG Skill for ChromaDB (PROJ-269 – PROJ-273)
# ──────────────────────────────────────────────────────────────

from typing import Optional
from skills.base_skill import BaseSkill, SkillResult
from app.knowledge_base.retrieval import QueryRetriever
from app.knowledge_base.chroma_client import ChromaClientManager


class KnowledgeBaseSkill(BaseSkill):
    """Skill for querying vector embeddings and documents stored in ChromaDB."""

    name        = "knowledge_base"
    description = "Search local documents, notes, and vector embeddings in the ChromaDB Knowledge Base."
    triggers    = ["kb", "knowledge base", "stored document", "chromadb", "vector search", "internal docs", "lookup doc"]

    def __init__(self, retriever: Optional[QueryRetriever] = None):
        self.retriever = retriever or QueryRetriever()

    def run(self, query: str) -> SkillResult:
        """Search the Knowledge Base for matching vector chunks."""
        search_res = self.retriever.search(query=query, n_results=5)

        raw_results = [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "title": item.title,
                "source": item.source,
                "text": item.text,
                "score": item.score,
                "distance": item.distance,
                "metadata": item.metadata,
            }
            for item in search_res.results
        ]

        if search_res.results_count == 0:
            summary = f"No relevant documents found in the Knowledge Base for '{query}'."
        else:
            top_match = search_res.results[0]
            summary = (
                f"Found {search_res.results_count} relevant document chunk(s) in Knowledge Base. "
                f"Top match: '{top_match.title}' (Score: {top_match.score:.2f})."
            )

        return SkillResult(
            skill_name=self.name,
            query=query,
            success=True,
            results=raw_results,
            summary=summary,
            duration_sec=search_res.duration_sec,
            metadata={"count": search_res.results_count}
        )
