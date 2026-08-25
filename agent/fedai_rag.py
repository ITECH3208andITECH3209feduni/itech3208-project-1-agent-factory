# agent/fedai_rag.py
# ──────────────────────────────────────────────────────────────
# Real semantic RAG for FedAI — the thing config/settings.py's
# FAQ_DATA_PATH comment has been waiting for ("swap in real embeddings
# + vector search once there's a real document corpus to index").
#
# Corpus: federation.edu.au + libanswers.federation.edu.au, crawled by
# a click-based Playwright crawler (the site is a JS SPA where deep
# pages 404 on direct URL load — see crawl scripts) and a sitemap-based
# crawler for LibAnswers. Public pages only; /staff/* and anything
# behind login is excluded at crawl time.
#
# Stack: sentence-transformers (local, free, no API cost) for
# embeddings + ChromaDB (free, open-source, embedded — no server to
# run) for the vector store. Both persist to disk under outputs/.
# ──────────────────────────────────────────────────────────────

import math
import os
import re

import chromadb
from sentence_transformers import SentenceTransformer

from config.settings import FEDAI_CHROMA_DIR, FEDAI_EMBED_MODEL

COLLECTION_NAME = "fedai_site"
CHUNK_WORDS = 350
CHUNK_OVERLAP = 60

_model = None
_client = None
_collection = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(FEDAI_EMBED_MODEL)
    return _model


def _get_collection():
    global _client, _collection
    if _collection is None:
        os.makedirs(FEDAI_CHROMA_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=FEDAI_CHROMA_DIR)
        _collection = _client.get_or_create_collection(
            COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )
    return _collection


# ── Parsing crawled page files ───────────────────────────────────

def _clean_libanswers_text(text: str) -> str:
    """LibAnswers FAQ pages embed the full topic-browse sidebar and
    footer chrome as plain text (not semantic <nav>, so a generic
    boilerplate strip misses it). Real Q&A content consistently sits
    between the 'Question' marker and 'Toggle action bar'. Falls back
    to the raw text if the markers aren't found, rather than dropping
    content we can't confidently trim."""
    start_marker = "\nQuestion\n"
    end_marker = "\nToggle action bar"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start != -1 and end != -1 and end > start:
        return text[start + len(start_marker) : end].strip()
    return text


_FEDSITE_HEADER_LINES = {
    "skip to main", "home", "current students", "staff", "library",
    "contact us", "study", "apply", "research", "engage", "about",
    "open day", "search", "services", "our libraries",
}
_FEDSITE_FOOTER_MARKER = "Federation University Australia acknowledges the Traditional Custodians"


def _clean_fedsite_text(text: str) -> str:
    """Every federation.edu.au page carries the same global nav (Skip to
    main / Home / Current students / ... ) and a large repeated footer
    (Acknowledgement of Country, contact numbers, site nav, copyright).
    Identical boilerplate on ~1,000+ pages dilutes chunk embeddings and
    hurts retrieval relevance corpus-wide, not just for any one page —
    strip both before chunking."""
    footer_idx = text.find(_FEDSITE_FOOTER_MARKER)
    if footer_idx != -1:
        text = text[:footer_idx]

    lines = text.split("\n")
    cut = 0
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if stripped == "" or stripped in _FEDSITE_HEADER_LINES:
            cut = i + 1
        else:
            break
    return "\n".join(lines[cut:]).strip()


def parse_page_file(path: str) -> dict | None:
    """Our crawlers write pages as:
        URL: <url>
        TITLE: <title>
        DEPTH: <n>            (or LASTMOD: ... for the sitemap crawler)
        ---
        <body text>
    Returns {"url", "title", "text"} or None if unparseable."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    if "---\n" not in raw:
        return None
    header, body = raw.split("---\n", 1)

    url_match = re.search(r"^URL: (.+)$", header, re.MULTILINE)
    title_match = re.search(r"^TITLE: (.+)$", header, re.MULTILINE)
    if not url_match:
        return None

    url = url_match.group(1).strip()
    text = body.strip()
    if "libanswers.federation.edu.au" in url:
        text = _clean_libanswers_text(text)
    else:
        text = _clean_fedsite_text(text)

    return {
        "url": url,
        "title": title_match.group(1).strip() if title_match else "",
        "text": text,
    }


def chunk_text(text: str, chunk_words: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Word-based chunking with overlap. FAQ-style short pages naturally
    end up as a single chunk; long pages get split so retrieval can
    return a focused slice instead of a whole page."""
    words = text.split()
    if len(words) <= chunk_words:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_words
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap
    return chunks


# ── Index build ───────────────────────────────────────────────────

def build_index(page_dirs: list[str], reset: bool = True) -> dict:
    """Reads every .txt page file under page_dirs, chunks it, embeds
    every chunk, and writes it into the Chroma collection.

    reset=True wipes the existing collection first — safe/expected
    when re-running after a crawl adds more pages, since chunk IDs are
    derived from (url, chunk_index) and stay stable otherwise, but a
    full rebuild is simplest to reason about for a corpus this size.
    """
    global _collection, _all_chunks_cache
    _all_chunks_cache = None  # invalidate — stale after a rebuild
    os.makedirs(FEDAI_CHROMA_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=FEDAI_CHROMA_DIR)

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    collection = client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )
    _collection = collection

    model = _get_model()

    seen_urls = set()
    pages_indexed = 0
    chunks_indexed = 0
    skipped_duplicate = 0
    skipped_empty = 0

    all_ids, all_docs, all_metas = [], [], []

    for page_dir in page_dirs:
        if not os.path.isdir(page_dir):
            continue
        for fname in sorted(os.listdir(page_dir)):
            if not fname.endswith(".txt"):
                continue
            path = os.path.join(page_dir, fname)
            parsed = parse_page_file(path)
            if not parsed:
                continue

            if parsed["url"] in seen_urls:
                skipped_duplicate += 1
                continue
            seen_urls.add(parsed["url"])

            chunks = chunk_text(parsed["text"])
            if not chunks:
                skipped_empty += 1
                continue

            pages_indexed += 1
            for i, chunk in enumerate(chunks):
                all_ids.append(f"{parsed['url']}#{i}")
                all_docs.append(chunk)
                all_metas.append({"url": parsed["url"], "title": parsed["title"], "chunk_index": i})
                chunks_indexed += 1

    # Embed + upsert in batches (embedding all at once is fine at this
    # corpus size — a few hundred pages, low thousands of chunks).
    BATCH = 128
    for i in range(0, len(all_docs), BATCH):
        batch_docs = all_docs[i : i + BATCH]
        batch_ids = all_ids[i : i + BATCH]
        batch_metas = all_metas[i : i + BATCH]
        embeddings = model.encode(batch_docs, show_progress_bar=False).tolist()
        collection.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_metas, embeddings=embeddings)

    return {
        "pages_indexed": pages_indexed,
        "chunks_indexed": chunks_indexed,
        "skipped_duplicate_url": skipped_duplicate,
        "skipped_empty": skipped_empty,
    }


# ── Retrieval ─────────────────────────────────────────────────────

_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "did", "what", "how",
    "when", "where", "why", "can", "could", "would", "should", "i",
    "you", "your", "to", "for", "of", "on", "in", "my", "me", "and",
    "or", "it", "this", "that", "with", "have", "has", "will", "be",
    "at", "there", "any", "about",
}

_all_chunks_cache = None


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _load_all_chunks() -> list[dict]:
    """Pulls every chunk into memory once for keyword scoring. Corpus is
    a few thousand chunks — cheap to hold and scan in-memory per query."""
    global _all_chunks_cache
    if _all_chunks_cache is not None:
        return _all_chunks_cache

    collection = _get_collection()
    if collection.count() == 0:
        _all_chunks_cache = []
        return _all_chunks_cache

    got = collection.get(include=["documents", "metadatas"])
    chunks = []
    for chunk_id, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
        chunks.append({"id": chunk_id, "text": doc, "meta": meta, "tokens": _tokenize(doc)})
    _all_chunks_cache = chunks
    return chunks


def _keyword_search(query: str, k: int) -> dict[str, float]:
    """IDF-weighted token-overlap score per chunk id. Exists to catch
    cases the embedding model misses — rare proper nouns (a cafe's actual
    name, a building code) that a small local embedding model doesn't
    strongly associate with the surrounding topic, even though a plain
    keyword match makes the chunk obviously relevant.

    Plain unweighted overlap (matched tokens / query tokens) doesn't work
    here: a common word like "hours" appears in hundreds of chunks and
    would score identically to matching "murnong", a name that appears in
    only 3 — so a page that happens to mention "hours" for something
    unrelated ties with, or beats, the one actually about that café. IDF
    weighting fixes this the standard way: a token's contribution to the
    score is inversely proportional to how many chunks contain it, so the
    rare, distinctive word decides the ranking, not the common one."""
    q_tokens = _tokenize(query)
    if not q_tokens:
        return {}

    chunks = _load_all_chunks()
    n_chunks = len(chunks)

    doc_freq = {tok: 0 for tok in q_tokens}
    for chunk in chunks:
        for tok in q_tokens:
            if tok in chunk["tokens"]:
                doc_freq[tok] += 1

    idf = {tok: math.log((n_chunks + 1) / (doc_freq[tok] + 1)) + 1 for tok in q_tokens}
    max_possible = sum(idf.values())

    scored = []
    for chunk in chunks:
        overlap = q_tokens & chunk["tokens"]
        if not overlap:
            continue
        score = sum(idf[tok] for tok in overlap) / max_possible
        scored.append((chunk["id"], score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return dict(scored[:k])


def retrieve(query: str, k: int = 5) -> list[dict]:
    """Hybrid retrieval: semantic (embedding) search + keyword overlap
    search, merged by taking the best of either score per chunk. Pure
    semantic search alone under-retrieves on rare proper nouns (e.g. a
    café's actual name) that the small local embedding model doesn't
    strongly associate with related terms — keyword search reliably
    catches those since it's just checking whether the word is literally
    present. Returns the top-k most relevant chunks with source URL/title.
    Empty list if the index hasn't been built."""
    collection = _get_collection()
    if collection.count() == 0:
        return []

    # Widen the semantic candidate pool beyond k so keyword-boosted chunks
    # that rank outside a bare top-k still get a chance to surface.
    pool = min(max(k * 4, 20), collection.count())

    model = _get_model()
    query_embedding = model.encode([query]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=pool)

    semantic_scores: dict[str, float] = {}
    chunk_data: dict[str, dict] = {}
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]
    for cid, doc, meta, dist in zip(ids, docs, metas, dists):
        semantic_scores[cid] = 1 - dist
        chunk_data[cid] = {"text": doc, "url": meta.get("url", ""), "title": meta.get("title", "")}

    keyword_scores = _keyword_search(query, k=pool)
    for cid, score in keyword_scores.items():
        if cid not in chunk_data:
            chunk = next((c for c in _load_all_chunks() if c["id"] == cid), None)
            if chunk:
                chunk_data[cid] = {"text": chunk["text"], "url": chunk["meta"].get("url", ""),
                                    "title": chunk["meta"].get("title", "")}

    all_ids = sorted(set(semantic_scores) | set(keyword_scores))  # deterministic base order
    combined = []
    for cid in all_ids:
        sem = semantic_scores.get(cid, 0.0)
        kw = keyword_scores.get(cid, 0.0)
        combined_score = max(sem, kw)
        combined.append((cid, combined_score, sem, kw))

    # Tie-break on the other signal, so equal top-line scores don't fall
    # back to arbitrary insertion order.
    combined.sort(key=lambda x: (x[1], x[2], x[3]), reverse=True)

    out = []
    for cid, score, sem, kw in combined[:k]:
        data = chunk_data[cid]
        out.append({
            "id": cid,
            "text": data["text"],
            "url": data["url"],
            "title": data["title"],
            "relevance": round(score, 3),
        })
    return out


def build_rag_context(query: str, k: int = 5) -> str:
    """Formats retrieved chunks for injection into a system prompt.

    Expands each hit with its immediate sibling chunks from the same
    page. A short page that got split into 2-3 chunks can have its
    answer-bearing chunk score lower for a given phrasing than a
    neighboring chunk from the same page (e.g. a café's opening-hours
    list vs. that same page's dining-events section) — without this, the
    model can end up with only the wrong half of a page it clearly needed
    in full. Chunks from the same URL are merged into one block instead
    of repeating the source header per chunk."""
    hits = retrieve(query, k=k)
    if not hits:
        return ""

    chunks_by_id = {c["id"]: c for c in _load_all_chunks()}

    pages: dict[str, dict] = {}
    page_order: list[str] = []
    for h in hits:
        url, _, idx_str = h["id"].rpartition("#")
        try:
            idx = int(idx_str)
        except ValueError:
            url, idx = h["id"], 0

        if url not in pages:
            pages[url] = {"title": h["title"], "indices": set()}
            page_order.append(url)
        pages[url]["indices"].add(idx)
        for sibling in (idx - 1, idx + 1):
            if f"{url}#{sibling}" in chunks_by_id:
                pages[url]["indices"].add(sibling)

    parts = []
    for url in page_order:
        info = pages[url]
        ordered_text = []
        for idx in sorted(info["indices"]):
            chunk = chunks_by_id.get(f"{url}#{idx}")
            if chunk:
                ordered_text.append(chunk["text"])
        parts.append(f"[Source: {info['title']} — {url}]\n" + "\n".join(ordered_text))

    return "\n\n".join(parts)
