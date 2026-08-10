# agent/kb_store.py
# ──────────────────────────────────────────────────────────────
# Knowledge Base document store for the Web UI's "Knowledge Base"
# tab (PROJ-279-283).
#
# Scope, stated honestly: this is upload / list / delete / search-test
# for per-user documents. It does NOT wire uploaded documents into the
# literature/amazon orchestrator's answers (no RAG augmentation) — the
# ticket asks for the management tab itself ("file upload strip;
# document list with delete button; search test input"), not for the
# research skills to start citing uploaded docs. That's a reasonable
# follow-up, not something silently assumed done here.
#
# Storage: SQLite (same pattern as agent/auth.py, agent/memory.py) —
# one row per document, full text content stored inline (these are
# small user-uploaded text/markdown files, not a document warehouse).
#
# Search: keyword/token-overlap scoring, same honestly-scoped approach
# as agent/faq.py — NOT ChromaDB / embeddings. See faq.py's docstring
# for why: standing up real vector search needs a document corpus to
# validate against, which doesn't exist yet either.
# ──────────────────────────────────────────────────────────────

import os
import re
import sqlite3
from datetime import datetime

from config.settings import KB_DB

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL,
    filename    TEXT NOT NULL,
    content     TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL
);
"""

# Text-decodable extensions we'll accept and index. Anything else is
# rejected up front rather than stored as an unreadable blob nobody
# can search — a real "any file type" pipeline needs PDF/DOCX text
# extraction, which isn't part of this ticket's scope.
ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".json"}
MAX_CONTENT_BYTES = 2_000_000  # 2MB per document — generous for text/markdown

_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "did", "what", "how",
    "when", "where", "why", "can", "could", "would", "should", "i",
    "you", "your", "to", "for", "of", "on", "in", "my", "me", "and",
    "or", "it", "this", "that", "with", "have", "has", "will", "be",
}


class KBError(Exception):
    """Raised for validation failures with a user-facing message."""


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(KB_DB), exist_ok=True)
    conn = sqlite3.connect(KB_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


# ── CRUD ─────────────────────────────────────────────────────────


def add_document(username: str, filename: str, raw_bytes: bytes) -> dict:
    """Validate, decode, and store an uploaded document. Returns the
    stored row as a dict. Raises KBError on invalid input."""
    if not filename:
        raise KBError("Filename is required.")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise KBError(
            f"Unsupported file type '{ext or '(none)'}'. "
            f"Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
    if len(raw_bytes) == 0:
        raise KBError("File is empty.")
    if len(raw_bytes) > MAX_CONTENT_BYTES:
        raise KBError(f"File too large — max {MAX_CONTENT_BYTES // 1_000_000}MB.")

    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise KBError("File isn't valid UTF-8 text.")

    safe_name = os.path.basename(filename)  # strip any path components
    now = datetime.now().isoformat()

    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kb_documents (username, filename, content, size_bytes, uploaded_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (username, safe_name, content, len(raw_bytes), now),
        )
        conn.commit()
        doc_id = cur.lastrowid
    finally:
        conn.close()

    return {
        "id": doc_id,
        "filename": safe_name,
        "size_bytes": len(raw_bytes),
        "uploaded_at": now,
    }


def list_documents(username: str) -> list[dict]:
    """Return metadata (no content) for all of a user's documents,
    newest first."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, filename, size_bytes, uploaded_at FROM kb_documents"
            " WHERE username = ? ORDER BY uploaded_at DESC",
            (username,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def list_documents_with_content(username: str) -> list[dict]:
    """Same as list_documents but includes full content — used by the
    integrity checker's KB-plagiarism comparison (agent/integrity.py).
    Kept separate from list_documents so the /kb/list endpoint (which
    powers the document list UI) never accidentally ships full file
    contents to the browser."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, filename, content, size_bytes, uploaded_at FROM kb_documents"
            " WHERE username = ? ORDER BY uploaded_at DESC",
            (username,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def delete_document(username: str, doc_id: int) -> bool:
    """Delete a document if it belongs to username. Returns True if a
    row was deleted, False if not found / not owned by this user."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM kb_documents WHERE id = ? AND username = ?",
            (doc_id, username),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def search_documents(username: str, query: str, limit: int = 5) -> list[dict]:
    """Keyword-overlap search over a user's own documents. Returns a
    list of {id, filename, score, snippet} ordered by score desc.
    See module docstring: this is NOT semantic/embedding search."""
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, filename, content FROM kb_documents WHERE username = ?",
            (username,),
        ).fetchall()
    finally:
        conn.close()

    scored: list[dict] = []
    for row in rows:
        doc_tokens = _tokenize(row["content"])
        overlap = q_tokens & doc_tokens
        if not overlap:
            continue
        score = len(overlap) / len(q_tokens)
        snippet = _make_snippet(row["content"], q_tokens)
        scored.append(
            {
                "id": row["id"],
                "filename": row["filename"],
                "score": round(score, 3),
                "snippet": snippet,
            }
        )

    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored[:limit]


def _make_snippet(content: str, q_tokens: set[str], width: int = 160) -> str:
    """Return a short excerpt centred on the first matched query term,
    so search results show *why* they matched instead of just the
    start of the file."""
    lower = content.lower()
    best_idx = -1
    for tok in q_tokens:
        idx = lower.find(tok)
        if idx != -1 and (best_idx == -1 or idx < best_idx):
            best_idx = idx
    if best_idx == -1:
        excerpt = content[:width]
    else:
        start = max(0, best_idx - width // 2)
        excerpt = content[start : start + width]
    excerpt = excerpt.strip().replace("\n", " ")
    return (excerpt + "…") if len(excerpt) == width else excerpt
