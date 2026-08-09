# app/knowledge_base/ingestion.py
# ──────────────────────────────────────────────────────────────
# Document Ingestion Pipeline (PROJ-264 – PROJ-268)
# ──────────────────────────────────────────────────────────────

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.knowledge_base.chroma_client import ChromaClientManager
from config.settings import DEFAULT_KB_COLLECTION

logger = logging.getLogger(__name__)


@dataclass
class DocumentInput:
    """Input payload for ingesting a document into the Knowledge Base."""
    content: str
    title: str = "Untitled Document"
    source: str = "user_upload"
    document_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestionResult:
    """Status report for a document ingestion operation."""
    document_id: str
    title: str
    chunks_count: int
    success: bool
    error: str = ""
    duration_sec: float = 0.0


class TextChunker:
    """Splits documents into overlapping chunks for embedding."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = max(100, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))

    def split_text(self, text: str) -> list[str]:
        """Split text into chunks aiming for paragraph/sentence boundaries."""
        if not text or not text.strip():
            return []

        text = text.strip()
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + self.chunk_size
            if end >= text_length:
                chunks.append(text[start:].strip())
                break

            # Try to break at paragraph boundary, then sentence boundary, then space
            break_pos = text.rfind("\n\n", start, end)
            if break_pos == -1 or break_pos < start + (self.chunk_size // 2):
                break_pos = text.rfind(". ", start, end)
                if break_pos != -1:
                    break_pos += 1  # Include period
            if break_pos == -1 or break_pos < start + (self.chunk_size // 2):
                break_pos = text.rfind(" ", start, end)

            if break_pos == -1 or break_pos <= start:
                break_pos = end

            chunk = text[start:break_pos].strip()
            if chunk:
                chunks.append(chunk)

            # Move forward with overlap
            start = break_pos - self.chunk_overlap if break_pos > start + self.chunk_overlap else break_pos

        return chunks


class DocumentParser:
    """Parses raw text, JSON, or markdown strings into standardized DocumentInput objects."""

    @staticmethod
    def parse(content: str, title: str = "Untitled Document", source: str = "text", metadata: Optional[dict] = None) -> DocumentInput:
        meta = metadata or {}
        # Try parsing JSON if content looks like JSON
        if content.strip().startswith("{") and content.strip().endswith("}"):
            try:
                data = json.loads(content)
                parsed_title = data.get("title", title)
                parsed_content = data.get("content", data.get("abstract", data.get("text", content)))
                parsed_source = data.get("source", source)
                return DocumentInput(
                    content=str(parsed_content),
                    title=str(parsed_title),
                    source=str(parsed_source),
                    metadata=meta
                )
            except Exception:
                pass

        return DocumentInput(content=content, title=title, source=source, metadata=meta)


class DocumentIngestor:
    """Ingests processed documents into ChromaDB collection."""

    def __init__(
        self,
        client_manager: Optional[ChromaClientManager] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ):
        self.client_manager = client_manager or ChromaClientManager()
        self.chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def ingest_document(
        self,
        doc_input: DocumentInput,
        collection_name: str = DEFAULT_KB_COLLECTION
    ) -> IngestionResult:
        """Ingest a single document into ChromaDB collection."""
        start_time = time.time()

        # Generate deterministic document ID if not provided
        doc_id = doc_input.document_id
        if not doc_id:
            hash_input = f"{doc_input.title}:{doc_input.content[:200]}"
            doc_id = "doc_" + hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:12]

        chunks = self.chunker.split_text(doc_input.content)
        if not chunks:
            return IngestionResult(
                document_id=doc_id,
                title=doc_input.title,
                chunks_count=0,
                success=False,
                error="Document content is empty after processing.",
                duration_sec=round(time.time() - start_time, 3)
            )

        try:
            collection = self.client_manager.get_or_create_collection(collection_name)

            chunk_ids = []
            chunk_texts = []
            chunk_metadatas = []

            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            for idx, chunk_text in enumerate(chunks):
                chunk_id = f"{doc_id}_chunk_{idx}"
                meta = {
                    "document_id": doc_id,
                    "title": doc_input.title,
                    "source": doc_input.source,
                    "chunk_index": idx,
                    "total_chunks": len(chunks),
                    "created_at": now_iso,
                    **{k: str(v) for k, v in doc_input.metadata.items()}  # Chroma metadata values must be primitive
                }

                chunk_ids.append(chunk_id)
                chunk_texts.append(chunk_text)
                chunk_metadatas.append(meta)

            collection.add(
                ids=chunk_ids,
                documents=chunk_texts,
                metadatas=chunk_metadatas
            )

            duration = round(time.time() - start_time, 3)
            logger.info(f"Successfully ingested document '{doc_input.title}' ({len(chunks)} chunks, ID: {doc_id})")

            return IngestionResult(
                document_id=doc_id,
                title=doc_input.title,
                chunks_count=len(chunks),
                success=True,
                duration_sec=duration
            )

        except Exception as e:
            logger.error(f"Failed to ingest document '{doc_input.title}': {e}", exc_info=True)
            return IngestionResult(
                document_id=doc_id,
                title=doc_input.title,
                chunks_count=0,
                success=False,
                error=str(e),
                duration_sec=round(time.time() - start_time, 3)
            )
