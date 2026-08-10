# agent/integrity.py
# ──────────────────────────────────────────────────────────────
# Backend for the Web UI's "Integrity Check" tab (PROJ-364-368).
#
# Honest scope note, read this before trusting the output:
#
# 1. AI-authorship score is a RULE-BASED HEURISTIC, not a trained
#    classifier and not a call to a third-party detector (Turnitin,
#    GPTZero, Originality.ai, etc.). It looks at surface stylometric
#    signals — sentence-length variance, lexical diversity, and the
#    frequency of formulaic transition phrases that are over-
#    represented in a lot of generic LLM output ("furthermore",
#    "in conclusion", "it is important to note", ...). These signals
#    are real and measurable, but they are weak and gameable: a
#    careful human writer can trip them, and a lightly-edited AI
#    draft can dodge them. Independent research on commercial AI-text
#    detectors (the well-resourced ones, not this) has found high
#    false-positive rates, especially on non-native-English writing.
#    Treat `ai_probability` as "how templated does this look", a
#    signal to prompt a closer human read — never as a verdict, and
#    never as the sole basis for an academic-integrity finding.
#
# 2. Plagiarism check compares the submitted text against the
#    CURRENT USER'S OWN uploaded Knowledge Base documents
#    (agent/kb_store.py) using shingled (n-gram) overlap. It is not a
#    web-wide or institutional-corpus plagiarism scan — there's no
#    crawled index or external API wired in here. If nothing has been
#    uploaded to the KB, this half of the check will never find a
#    match, by design, not by bug.
#
# Both limitations are surfaced in the API response's `details` list
# so the frontend (and whoever's reading the result) sees them, not
# just this docstring.
# ──────────────────────────────────────────────────────────────

import re
import statistics

MIN_WORDS = 50

# Phrases disproportionately common in generic/unedited LLM output.
# Not exhaustive, not proof of anything on their own — see docstring.
_FORMULAIC_PHRASES = [
    "furthermore", "moreover", "in conclusion", "it is important to note",
    "it's important to note", "in today's fast-paced world", "overall,",
    "additionally,", "as a result,", "in summary,", "on the other hand,",
    "this highlights", "plays a crucial role", "plays a vital role",
    "delve into", "in the realm of", "it is worth noting",
    "in order to", "a testament to", "underscores the importance",
]

# Sentence length band typical of a lot of default LLM prose — used
# as one weak signal among several, not a threshold on its own.
_AI_TYPICAL_SENTENCE_LEN = (14, 24)


def _split_sentences(text: str) -> list[str]:
    # Simple, dependency-free sentence splitter — good enough for a
    # heuristic; not meant to handle every edge case (abbreviations,
    # decimals, etc.) perfectly.
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in raw if s.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text)


def _shingles(text: str, n: int = 8) -> set[str]:
    """Word n-grams ('shingles'), lowercased — used for the KB
    plagiarism overlap check. n=8 keeps false-positive matches on
    common short phrases low while still catching paraphrase-light
    copying."""
    words = [w.lower() for w in _words(text)]
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def _lexical_diversity(words: list[str]) -> float:
    if not words:
        return 0.0
    lowered = [w.lower() for w in words]
    return len(set(lowered)) / len(lowered)


def _formulaic_density(text: str) -> float:
    """Formulaic-phrase hits per 100 words."""
    lower = text.lower()
    hits = sum(lower.count(p) for p in _FORMULAIC_PHRASES)
    word_count = max(len(_words(text)), 1)
    return hits / word_count * 100


def _sentence_length_signal(sentence_lengths: list[int]) -> tuple[float, float]:
    """Returns (burstiness_score, band_score), each 0-1.

    burstiness_score: human writing tends to mix short and long
    sentences more than default LLM prose does. Low variance (relative
    to mean) => higher AI-likeness score here.

    band_score: fraction of sentences that fall inside the "typical
    LLM sentence length" band defined above.
    """
    if len(sentence_lengths) < 2:
        return 0.0, 0.0

    mean = statistics.mean(sentence_lengths)
    stdev = statistics.pstdev(sentence_lengths)
    cv = (stdev / mean) if mean else 0  # coefficient of variation

    # Empirically, human paragraphs often land around cv ~ 0.5-0.9;
    # very uniform sentence lengths (cv < 0.35) nudge the score up.
    burstiness_score = max(0.0, min(1.0, (0.55 - cv) / 0.55)) if cv < 0.55 else 0.0

    lo, hi = _AI_TYPICAL_SENTENCE_LEN
    in_band = sum(1 for length in sentence_lengths if lo <= length <= hi)
    band_score = in_band / len(sentence_lengths)

    return burstiness_score, band_score


class IntegrityError(Exception):
    """Raised for validation failures with a user-facing message."""


def check_ai_authorship(text: str) -> dict:
    """Compute the heuristic AI-authorship score for `text`.

    Returns {"ai_probability": float in [0,1], "signals": {...}} —
    `signals` is included so the API can surface *why*, not just a
    bare number (see docstring: this must never be presented as an
    unexplained verdict).
    """
    words = _words(text)
    if len(words) < MIN_WORDS:
        raise IntegrityError(
            f"Please provide at least {MIN_WORDS} words for a reliable analysis "
            f"(got {len(words)})."
        )

    sentences = _split_sentences(text)
    sentence_lengths = [len(_words(s)) for s in sentences if _words(s)]

    diversity = _lexical_diversity(words)
    # Lower diversity => more repetitive vocabulary => higher score.
    diversity_score = max(0.0, min(1.0, (0.55 - diversity) / 0.35)) if diversity < 0.55 else 0.0

    formulaic = _formulaic_density(text)
    # 0 hits/100words -> 0, 3+ hits/100words -> capped at 1.
    formulaic_score = max(0.0, min(1.0, formulaic / 3.0))

    burstiness_score, band_score = _sentence_length_signal(sentence_lengths)

    # Weighted blend — weights are a design choice, not a fitted
    # model. Formulaic phrasing is the single most legible signal, so
    # it carries the most weight; sentence-length signals are noisier
    # so they carry less.
    ai_probability = (
        0.35 * formulaic_score
        + 0.25 * diversity_score
        + 0.25 * burstiness_score
        + 0.15 * band_score
    )
    ai_probability = round(max(0.0, min(1.0, ai_probability)), 3)

    return {
        "ai_probability": ai_probability,
        "signals": {
            "word_count": len(words),
            "sentence_count": len(sentences),
            "lexical_diversity": round(diversity, 3),
            "formulaic_phrase_hits_per_100_words": round(formulaic, 2),
            "sentence_length_burstiness_score": round(burstiness_score, 3),
            "sentence_length_band_score": round(band_score, 3),
        },
    }


def check_plagiarism_against_kb(text: str, kb_documents: list[dict], threshold: float = 0.12) -> list[dict]:
    """Compare `text` against a list of {"id", "filename", "content"}
    dicts (the current user's own KB documents) using shingle
    (n-gram) Jaccard overlap. Returns matches at or above `threshold`,
    sorted by overlap desc. Empty list is a legitimate result, not an
    error — most callers will have an empty/no-match KB."""
    text_shingles = _shingles(text)
    if not text_shingles:
        return []

    matches = []
    for doc in kb_documents:
        doc_shingles = _shingles(doc.get("content", ""))
        if not doc_shingles:
            continue
        overlap = text_shingles & doc_shingles
        if not overlap:
            continue
        # Jaccard-style overlap, but normalized against the *smaller*
        # set so that checking a short paragraph against a long
        # reference document isn't automatically diluted to ~0 —
        # what matters for plagiarism is "how much of the submitted
        # text is covered", not overlap over the union of both.
        smaller = min(len(text_shingles), len(doc_shingles))
        overlap_ratio = len(overlap) / smaller if smaller else 0.0
        if overlap_ratio >= threshold:
            matches.append(
                {
                    "id": doc.get("id"),
                    "filename": doc.get("filename"),
                    "overlap_ratio": round(overlap_ratio, 3),
                }
            )

    matches.sort(key=lambda m: m["overlap_ratio"], reverse=True)
    return matches


def run_integrity_check(text: str, kb_documents: list[dict]) -> dict:
    """Full check: AI-authorship heuristic + KB plagiarism scan.
    Raises IntegrityError (400-worthy) if `text` is too short.
    Returns the shape the Web UI's renderIntegrityResult() expects:
    {ai_probability, summary, details}."""
    ai_result = check_ai_authorship(text)
    matches = check_plagiarism_against_kb(text, kb_documents)

    details = [
        "AI-authorship score is a rule-based heuristic (sentence-length "
        "variance, vocabulary diversity, formulaic-phrase frequency) — "
        "not a trained classifier or third-party detector. Treat it as "
        "a prompt to look closer, not a verdict.",
        f"Signals: {ai_result['signals']['word_count']} words, "
        f"{ai_result['signals']['sentence_count']} sentences, "
        f"lexical diversity {ai_result['signals']['lexical_diversity']}, "
        f"{ai_result['signals']['formulaic_phrase_hits_per_100_words']} "
        "formulaic-phrase hits per 100 words.",
    ]

    if matches:
        for m in matches[:5]:
            details.append(
                f"Possible overlap with your Knowledge Base document "
                f"'{m['filename']}' (~{round(m['overlap_ratio'] * 100)}% "
                "shingle overlap)."
            )
    else:
        details.append(
            "No overlap found against your Knowledge Base documents. "
            "Note: this only checks documents you've uploaded to the KB "
            "tab — it is not a web-wide plagiarism scan."
        )

    pct = round(ai_result["ai_probability"] * 100)
    if matches:
        summary = (
            f"{pct}% AI-authorship heuristic score. Found possible overlap "
            f"with {len(matches)} of your Knowledge Base document(s) — see "
            "details below."
        )
    else:
        summary = (
            f"{pct}% AI-authorship heuristic score. No overlap found "
            "against your Knowledge Base documents."
        )

    return {
        "ai_probability": ai_result["ai_probability"],
        "summary": summary,
        "details": details,
    }
