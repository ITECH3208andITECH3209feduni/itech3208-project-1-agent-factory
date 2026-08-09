# api/routes/knowledge_base.py
# ──────────────────────────────────────────────────────────────
# Knowledge Base Management API (PROJ-274 – PROJ-278)
# ──────────────────────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Query, Path

from api.schemas import (
    KBIngestRequest,
    KBIngestResponse,
    KBQueryRequest,
    KBQueryResponse,
    KBDocumentChunk,
    KBDocumentSummary,
    KBDocumentListResponse,
)
from app.knowledge_base.ingestion import DocumentIngestor, DocumentInput
from app.knowledge_base.retrieval import QueryRetriever

router = APIRouter(prefix="/api/kb", tags=["knowledge_base"])

# Singletons for API handlers
_ingestor = DocumentIngestor()
_retriever = QueryRetriever()


@router.post("/ingest", response_model=KBIngestResponse, status_code=201)
def ingest_document(payload: KBIngestRequest) -> KBIngestResponse:
    """Ingest document text into the ChromaDB Knowledge Base vector store."""
    if not payload.content or not payload.content.strip():
        raise HTTPException(status_code=400, detail="Document content cannot be empty.")

    doc_input = DocumentInput(
        content=payload.content,
        title=payload.title,
        source=payload.source,
        document_id=payload.document_id,
        metadata=payload.metadata,
    )

    res = _ingestor.ingest_document(doc_input)
    if not res.success:
        raise HTTPException(status_code=500, detail=res.error or "Document ingestion failed.")

    return KBIngestResponse(
        document_id=res.document_id,
        title=res.title,
        chunks_count=res.chunks_count,
        success=res.success,
        duration_sec=res.duration_sec,
    )


@router.post("/query", response_model=KBQueryResponse)
def query_knowledge_base(payload: KBQueryRequest) -> KBQueryResponse:
    """Query the Knowledge Base using vector similarity search."""
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    search_res = _retriever.search(
        query=payload.query,
        n_results=payload.n_results,
        where=payload.where,
    )

    chunks = [
        KBDocumentChunk(
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            title=item.title,
            source=item.source,
            text=item.text,
            score=item.score,
            distance=item.distance,
            metadata=item.metadata,
        )
        for item in search_res.results
    ]

    return KBQueryResponse(
        query=payload.query,
        count=len(chunks),
        results=chunks,
        duration_sec=search_res.duration_sec,
    )


@router.get("/documents", response_model=KBDocumentListResponse)
def list_documents() -> KBDocumentListResponse:
    """List distinct document metadata stored in the Knowledge Base."""
    docs_raw = _retriever.list_documents()
    documents = [
        KBDocumentSummary(
            document_id=str(d.get("document_id", "")),
            title=str(d.get("title", "Untitled")),
            source=str(d.get("source", "unknown")),
            total_chunks=int(d.get("total_chunks", 1)),
            created_at=str(d.get("created_at", "")),
        )
        for d in docs_raw
    ]
    return KBDocumentListResponse(count=len(documents), documents=documents)


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str = Path(..., description="The ID of the document to delete")
) -> dict:
    """Delete a document and all its chunks from the Knowledge Base."""
    success = _retriever.delete_document(document_id=document_id)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to delete document '{document_id}'.")
    return {"message": f"Successfully deleted document '{document_id}'.", "document_id": document_id}
