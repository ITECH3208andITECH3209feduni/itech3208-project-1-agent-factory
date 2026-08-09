# app/knowledge_base/chroma_client.py
# ──────────────────────────────────────────────────────────────
# ChromaDB Client Setup & Management (PROJ-259 – PROJ-263)
# ──────────────────────────────────────────────────────────────

import os
import logging
from typing import Any, Optional

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None  # type: ignore

from config.settings import CHROMADB_DIR, DEFAULT_KB_COLLECTION

logger = logging.getLogger(__name__)


class ChromaClientManager:
    """Manages connection and collections for ChromaDB persistent vector storage."""

    def __init__(self, persist_directory: Optional[str] = None, in_memory: bool = False):
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb library is not installed. Run `pip install chromadb` to use Knowledge Base capabilities."
            )
        
        self.persist_directory = persist_directory or CHROMADB_DIR
        self.in_memory = in_memory

        if not self.in_memory:
            os.makedirs(self.persist_directory, exist_ok=True)
            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False)
            )
        else:
            self.client = chromadb.Client(
                settings=ChromaSettings(anonymized_telemetry=False)
            )

    def get_or_create_collection(
        self,
        name: str = DEFAULT_KB_COLLECTION,
        metadata: Optional[dict[str, Any]] = None
    ) -> Any:
        """Get an existing collection or create a new one."""
        meta = metadata or {"description": "Agent Factory Knowledge Base Vector Store", "hnsw:space": "cosine"}
        return self.client.get_or_create_collection(name=name, metadata=meta)

    def list_collections(self) -> list[str]:
        """List all collection names in ChromaDB."""
        collections = self.client.list_collections()
        return [c.name for c in collections]

    def get_collection_stats(self, name: str = DEFAULT_KB_COLLECTION) -> dict[str, Any]:
        """Get document count and metadata for a collection."""
        try:
            collection = self.client.get_collection(name=name)
            return {
                "name": name,
                "count": collection.count(),
                "metadata": collection.metadata,
                "exists": True
            }
        except Exception as e:
            logger.warning(f"Failed to get collection stats for {name}: {e}")
            return {"name": name, "count": 0, "metadata": {}, "exists": False}

    def delete_collection(self, name: str = DEFAULT_KB_COLLECTION) -> bool:
        """Delete a collection by name."""
        try:
            self.client.delete_collection(name=name)
            return True
        except Exception as e:
            logger.error(f"Error deleting collection {name}: {e}")
            return False

    def health_check(self) -> dict[str, Any]:
        """Check status of ChromaDB client."""
        try:
            cols = self.list_collections()
            return {
                "status": "ok",
                "available": True,
                "persist_directory": self.persist_directory if not self.in_memory else ":memory:",
                "collections_count": len(cols),
            }
        except Exception as e:
            return {
                "status": "error",
                "available": False,
                "error": str(e)
            }
