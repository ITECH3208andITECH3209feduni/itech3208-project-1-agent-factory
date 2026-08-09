# agent/faq.py
# ──────────────────────────────────────────────────────────────
# Keyword-overlap FAQ matcher for the AI Receptionist (PROJ-214-218)
#
# This is deliberately a stdlib-only placeholder, NOT the ChromaDB
# semantic search called for in the ticket spec. Standing this up with
# real vector search needs an actual document corpus to index first —
# until there's real KB content, a Jaccard token-overlap match over a
# small hand-written FAQ file is an honest, working v1 that's easy to
# swap out later without changing the call site (find_answer() below
# is the only thing agent/receptionist.py depends on).
# ──────────────────────────────────────────────────────────────

import json
import os
import re

from config.settings import FAQ_DATA_PATH, FAQ_MIN_SCORE

_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "did", "what", "how",
    "when", "where", "why", "can", "could", "would", "should", "i",
    "you", "your", "to", "for", "of", "on", "in", "my", "me", "and",
    "or", "it", "this", "that", "with", "have", "has", "will", "be",
}

_cache: list[dict] | None = None


def _load_faq() -> list[dict]:
    global _cache
    if _cache is not None:
        return _cache
    if not os.path.exists(FAQ_DATA_PATH):
        _cache = []
        return _cache
    try:
        with open(FAQ_DATA_PATH, encoding="utf-8") as fh:
            _cache = json.load(fh)
    except (json.JSONDecodeError, OSError):
        _cache = []
    return _cache


def reload_faq() -> None:
    """Drop the cache so the next find_answer() re-reads the JSON file
    from disk. Useful after editing config/faq_seed.json without
    restarting the server."""
    global _cache
    _cache = None


def _stem(word: str) -> str:
    """Crude suffix-stripping so 'opening'/'opens'/'open' and
    'hours'/'hour' land on the same token. Not a real stemmer (no
    Porter/Snowball dependency) — just enough normalisation for a
    small hand-written FAQ list."""
    for suffix in ("ing", "edly", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {_stem(w) for w in words if w not in _STOPWORDS and len(w) > 1}


def find_answer(query: str, min_score: float = None) -> dict | None:
    """Return the best-matching FAQ entry for query, or None if nothing
    clears the confidence threshold. Score is Jaccard similarity
    (token overlap / token union) between the query and each entry's
    question + tags."""
    threshold = FAQ_MIN_SCORE if min_score is None else min_score
    entries = _load_faq()
    if not entries:
        return None

    q_tokens = _tokenize(query)
    if not q_tokens:
        return None

    best: dict | None = None
    best_score = 0.0
    for entry in entries:
        candidate = entry.get("question", "") + " " + " ".join(entry.get("tags", []))
        e_tokens = _tokenize(candidate)
        if not e_tokens:
            continue
        overlap = q_tokens & e_tokens
        if not overlap:
            continue
        # Recall-weighted, not Jaccard: "what fraction of the user's own
        # meaningful words did this FAQ entry recognise". A short query
        # with 2-3 topic words shouldn't get diluted just because the
        # user also typed a few unrelated filler words.
        score = len(overlap) / len(q_tokens)
        if score > best_score:
            best, best_score = entry, score

    if best is not None and best_score >= threshold:
        return {**best, "score": round(best_score, 3)}
    return None
