# api/schemas.py
# ──────────────────────────────────────────────────────────────
# Pydantic schemas for REST API request/response shapes.
# ──────────────────────────────────────────────────────────────

from pydantic import BaseModel


class Paper(BaseModel):
    """A single paper result returned by GET /api/literature."""
    title:    str
    authors:  str = ""
    year:     str = ""
    abstract: str = ""
    source:   str
    url:      str = ""


class LiteratureResponse(BaseModel):
    """Response envelope for GET /api/literature."""
    query:  str
    count:  int
    papers: list[Paper]


class Product(BaseModel):
    """A single Amazon product result returned by GET /api/amazon."""
    title:  str
    price:  str = ""
    rating: str = ""
    asin:   str = ""
    url:    str = ""


class AmazonResponse(BaseModel):
    """Response envelope for GET /api/amazon."""
    query:    str
    count:    int
    products: list[Product]


# ── Knowledge Base (PROJ-274 – PROJ-278) ──────────────────────

class KBIngestRequest(BaseModel):
    """Request envelope for POST /api/kb/ingest."""
    content:     str
    title:       str = "Untitled Document"
    source:      str = "user_upload"
    document_id: str | None = None
    metadata:    dict = {}


class KBIngestResponse(BaseModel):
    """Response envelope for POST /api/kb/ingest."""
    document_id:  str
    title:        str
    chunks_count: int
    success:      bool
    error:        str = ""
    duration_sec: float = 0.0


class KBQueryRequest(BaseModel):
    """Request envelope for POST /api/kb/query."""
    query:     str
    n_results: int = 5
    where:     dict | None = None


class KBDocumentChunk(BaseModel):
    """Individual vector chunk in search response."""
    chunk_id:    str
    document_id: str
    title:       str
    source:      str
    text:        str
    score:       float
    distance:    float
    metadata:    dict = {}


class KBQueryResponse(BaseModel):
    """Response envelope for POST /api/kb/query."""
    query:        str
    count:        int
    results:      list[KBDocumentChunk]
    duration_sec: float = 0.0


class KBDocumentSummary(BaseModel):
    """Metadata summary for a single document stored in ChromaDB."""
    document_id:  str
    title:        str
    source:       str
    total_chunks: int = 1
    created_at:   str = ""


class KBDocumentListResponse(BaseModel):
    """Response envelope for GET /api/kb/documents."""
    count:     int
    documents: list[KBDocumentSummary]

