# app/knowledge_base/retrieval.py
# ──────────────────────────────────────────────────────────────
# Vector Query Retrieval Engine (PROJ-269 – PROJ-273)
# ──────────────────────────────────────────────────────────────

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.knowledge_base.chroma_client import ChromaClientManager
from config.settings import DEFAULT_KB_COLLECTION

logger = logging.getLogger(__name__)


@dataclass
class KBQueryResult:
    """Individual matching document chunk returned by vector retrieval."""
    chunk_id: str
    document_id: str
    title: str
    source: str
    text: str
    score: float
    distance: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResponse:
    """Envelope for vector query retrieval search results."""
    query: str
    results_count: int
    results: list[KBQueryResult]
    duration_sec: float = 0.0


class QueryRetriever:
    """Handles vector search queries and document management in ChromaDB."""

    def __init__(self, client_manager: Optional[ChromaClientManager] = None):
        self.client_manager = client_manager or ChromaClientManager()

    def search(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[dict[str, Any]] = None,
        collection_name: str = DEFAULT_KB_COLLECTION
    ) -> SearchResponse:
        """Execute vector similarity search for a query string."""
        start_time = time.time()
        if not query or not query.strip():
            return SearchResponse(query=query, results_count=0, results=[], duration_sec=0.0)

        try:
            collection = self.client_manager.get_or_create_collection(collection_name)
            if collection.count() == 0:
                return SearchResponse(
                    query=query,
                    results_count=0,
                    results=[],
                    duration_sec=round(time.time() - start_time, 3)
                )

            # Query ChromaDB collection
            raw_results = collection.query(
                query_texts=[query],
                n_results=min(n_results, collection.count()),
                where=where
            )

            results_list: list[KBQueryResult] = []

            if raw_results and raw_results.get("ids") and len(raw_results["ids"]) > 0:
                ids = raw_results["ids"][0]
                documents = raw_results["documents"][0] if raw_results.get("documents") else []
                metadatas = raw_results["metadatas"][0] if raw_results.get("metadatas") else []
                distances = raw_results["distances"][0] if raw_results.get("distances") else []

                for idx in range(len(ids)):
                    chunk_id = ids[idx]
                    text = documents[idx] if idx < len(documents) else ""
                    meta = metadatas[idx] if idx < len(metadatas) else {}
                    dist = distances[idx] if idx < len(distances) else 0.0

                    # Convert distance to normalized similarity score (cosine distance range [0, 2])
                    score = max(0.0, round(1.0 - (dist / 2.0 if dist <= 2.0 else dist), 4))

                    doc_id = str(meta.get("document_id", "unknown"))
                    title = str(meta.get("title", "Untitled"))
                    source = str(meta.get("source", "unknown"))

                    results_list.append(
                        KBQueryResult(
                            chunk_id=chunk_id,
                            document_id=doc_id,
                            title=title,
                            source=source,
                            text=text,
                            score=score,
                            distance=round(float(dist), 4),
                            metadata=meta
                        )
                    )

            duration = round(time.time() - start_time, 3)
            return SearchResponse(
                query=query,
                results_count=len(results_list),
                results=results_list,
                duration_sec=duration
            )

        except Exception as e:
            logger.error(f"Vector search failed for query '{query}': {e}", exc_info=True)
            return SearchResponse(
                query=query,
                results_count=0,
                results=[],
                duration_sec=round(time.time() - start_time, 3)
            )

    def list_documents(self, collection_name: str = DEFAULT_KB_COLLECTION) -> list[dict[str, Any]]:
        """List distinct document metadata stored in ChromaDB."""
        try:
            collection = self.client_manager.get_or_create_collection(collection_name)
            if collection.count() == 0:
                return []

            get_res = collection.get(include=["metadatas"])
            metadatas = get_res.get("metadatas", [])

            docs_map: dict[str, dict[str, Any]] = {}
            for meta in metadatas:
                if not meta:
                    continue
                doc_id = meta.get("document_id")
                if doc_id and doc_id not in docs_map:
                    docs_map[doc_id] = {
                        "document_id": doc_id,
                        "title": meta.get("title", "Untitled"),
                        "source": meta.get("source", "unknown"),
                        "total_chunks": meta.get("total_chunks", 1),
                        "created_at": meta.get("created_at", "")
                    }

            return list(docs_map.values())
        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []

    def delete_document(self, document_id: str, collection_name: str = DEFAULT_KB_COLLECTION) -> bool:
        """Delete all chunks belonging to a document_id."""
        try:
            collection = self.client_manager.get_or_create_collection(collection_name)
            collection.delete(where={"document_id": document_id})
            logger.info(f"Deleted document {document_id} from collection {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False
