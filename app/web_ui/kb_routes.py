# app/web_ui/kb_routes.py
# ──────────────────────────────────────────────────────────────
# Knowledge Base management endpoints (PROJ-279-283)
#
# Endpoints:
#   POST   /kb/upload        — upload a document (multipart file)
#   GET    /kb/list          — list current user's documents
#   DELETE /kb/{doc_id}      — delete a document (must be owned by caller)
#   GET    /kb/search?q=...  — keyword search over current user's documents
#
# All endpoints are login-protected and scoped to the calling user —
# one user can never see, search, or delete another user's documents.
# See agent/kb_store.py for storage + search implementation and its
# documented scope limits (text files only, keyword search not
# ChromaDB, no orchestrator RAG integration).
# ──────────────────────────────────────────────────────────────

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from agent.kb_store import (
    KBError,
    add_document,
    delete_document,
    list_documents,
    search_documents,
)
from app.web_ui.auth_routes import get_current_username

router = APIRouter(prefix="/kb", tags=["kb"])


class KBDocument(BaseModel):
    id: int
    filename: str
    size_bytes: int
    uploaded_at: str


class KBUploadResponse(BaseModel):
    ok: bool
    document: KBDocument


class KBListResponse(BaseModel):
    documents: list[KBDocument]


class KBSearchResult(BaseModel):
    id: int
    filename: str
    score: float
    snippet: str


class KBSearchResponse(BaseModel):
    query: str
    results: list[KBSearchResult]


@router.post("/upload", response_model=KBUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    username: str = Depends(get_current_username),
):
    raw_bytes = await file.read()
    try:
        doc = add_document(username, file.filename or "", raw_bytes)
    except KBError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return KBUploadResponse(ok=True, document=KBDocument(**doc))


@router.get("/list", response_model=KBListResponse)
async def list_kb_documents(username: str = Depends(get_current_username)):
    docs = list_documents(username)
    return KBListResponse(documents=[KBDocument(**d) for d in docs])


@router.delete("/{doc_id}")
async def delete_kb_document(
    doc_id: int, username: str = Depends(get_current_username)
):
    deleted = delete_document(username, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"ok": True}


@router.get("/search", response_model=KBSearchResponse)
async def search_kb(
    q: str = Query(..., min_length=1),
    username: str = Depends(get_current_username),
):
    results = search_documents(username, q)
    return KBSearchResponse(
        query=q, results=[KBSearchResult(**r) for r in results]
    )
