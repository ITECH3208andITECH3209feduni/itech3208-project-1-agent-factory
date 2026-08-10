# skills/academic_integrity.py
# ──────────────────────────────────────────────────────────────
# Academic Integrity Skill
# Implements PROJ-184, PROJ-185, PROJ-186
#
# PROJ-184: AI Content Detector — perplexity + burstiness analysis
#           + Claude classification (confidence 0-100%)
# PROJ-185: Plagiarism Scanner — DuckDuckGo Instant Answer API
#           phrase matching + similarity scoring
# PROJ-186: Academic Integrity Report — combined AI + plagiarism
#           analysis formatted as markdown
# ──────────────────────────────────────────────────────────────

import re
import math
import time
import requests
from collections import Counter
from urllib.parse import quote_plus

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from skills.base_skill import BaseSkill, SkillResult
from config.settings import (
    REQUEST_TIMEOUT,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_HAIKU_MODEL,
)

# ── DuckDuckGo Instant Answer API (no auth required) ──────────
DUCKDUCKGO_API_URL = "https://api.duckduckgo.com/"

# ── Mode detection keyword sets ───────────────────────────────
AI_DETECTION_TRIGGERS = {
    "detect ai", "ai written", "check if ai", "plagiarism check",
    "academic integrity", "ai detection", "gpt detection",
}
PLAGIARISM_TRIGGERS = {
    "plagiarism", "check plagiarism", "copied", "original", "duplicate content",
}
FULL_REPORT_TRIGGERS = {
    "integrity report", "full report", "academic report", "complete check",
}

# Minimum word count to analyse
MIN_WORD_COUNT = 50

# Number of sample phrases to search for plagiarism
PLAGIARISM_SAMPLE_COUNT = 5


class AcademicIntegritySkill(BaseSkill):
    """Detect AI-generated content, scan for plagiarism, and generate
    academic integrity reports (PROJ-184, PROJ-185, PROJ-186)."""

    name = "academic_integrity"
    description = (
        "Analyse text for academic integrity issues. Detects AI-generated content "
        "with confidence scoring, scans for plagiarism via web source matching, "
        "and generates comprehensive integrity reports. "
        "Use when the user asks about AI detection, plagiarism checking, "
        "or academic integrity of submitted text."
    )
    triggers = [
        "detect ai", "ai written", "check if ai", "plagiarism check",
        "academic integrity", "ai detection", "gpt detection",
        "plagiarism", "check plagiarism", "copied", "original",
        "duplicate content", "integrity report", "full report",
        "academic report", "complete check",
    ]

    _claude_client = None

    # ── Claude client ─────────────────────────────────────────
    @classmethod
    def _get_claude(cls):
        """Lazy-load the Anthropic client once."""
        if not ANTHROPIC_AVAILABLE:
            return None
        if cls._claude_client is None:
            try:
                cls._claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            except Exception:
                pass
        return cls._claude_client

    # ── Retry helper ──────────────────────────────────────────
    def _retry_get(
        self,
        url: str,
        params: dict = None,
        retries: int = 3,
        backoff: float = 2.0,
    ) -> requests.Response:
        """GET with automatic retry and exponential backoff."""
        last_error = None
        for attempt in range(retries):
            try:
                resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 429:
                    wait = backoff * (2 ** attempt)
                    time.sleep(wait)
                    last_error = Exception(f"HTTP 429 (waited {wait}s)")
                    continue
                resp.raise_for_status()
                return resp
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(backoff * (attempt + 1))
        raise last_error or Exception(f"Request failed after {retries} attempts")

    # ── Main entry point ──────────────────────────────────────
    def run(self, query: str) -> SkillResult:
        """Detect mode from the query, extract text, and dispatch to the
        appropriate analysis pipeline."""
        q_lower = query.lower()

        # ── Detect mode ───────────────────────────────────────
        mode = self._detect_mode(q_lower)

        # ── Extract text to analyse ───────────────────────────
        text = self._extract_text(query, mode)

        # ── Validate minimum length ───────────────────────────
        word_count = len(text.split()) if text else 0
        if word_count < MIN_WORD_COUNT:
            msg = "Please provide at least 50 words of text to analyze."
            return SkillResult(
                skill_name=self.name,
                query=query,
                success=False,
                error=msg,
                summary=msg,
                metadata={"mode": mode, "word_count": word_count},
            )

        # ── Dispatch to pipeline ──────────────────────────────
        if mode == "full_report":
            return self._run_full_report(query, text, word_count)
        elif mode == "plagiarism":
            return self._run_plagiarism(query, text, word_count)
        else:
            # Default: AI detection
            return self._run_ai_detection(query, text, word_count)

    # ── Mode detection ────────────────────────────────────────
    def _detect_mode(self, q_lower: str) -> str:
        """Return 'full_report', 'plagiarism', or 'ai_detection' based on
        keywords present in the lowercased query."""
        if any(t in q_lower for t in FULL_REPORT_TRIGGERS):
            return "full_report"
        if any(t in q_lower for t in PLAGIARISM_TRIGGERS):
            return "plagiarism"
        return "ai_detection"

    def _extract_text(self, query: str, mode: str) -> str:
        """Extract the body text that follows the first colon in the query.
        Falls back to the entire query if no colon is present."""
        if ":" in query:
            _, _, body = query.partition(":")
            return body.strip()
        return query.strip()

    # ── PROJ-184: AI Detection pipeline ──────────────────────
    def _run_ai_detection(
        self, query: str, text: str, word_count: int
    ) -> SkillResult:
        """Run AI content detection using statistical signals + Claude classification."""
        errors = []

        sentences = self._split_sentences(text)
        perplexity_score = self._calc_perplexity(text)
        burstiness_score = self._calc_burstiness(sentences)

        # Ask Claude to classify
        classification = "Uncertain"
        confidence_score = 0.5
        ai_probability = 0.5
        flagged_passages: list[str] = []
        explanation = ""

        client = self._get_claude()
        if client:
            try:
                claude_result = self._classify_with_claude(
                    text, perplexity_score, burstiness_score, sentences
                )
                classification = claude_result["classification"]
                confidence_score = claude_result["confidence_score"]
                ai_probability = claude_result["ai_probability"]
                flagged_passages = claude_result["flagged_passages"]
                explanation = claude_result["explanation"]
            except Exception as exc:
                errors.append(f"Claude classification: {exc}")
                # Heuristic fallback when Claude is unavailable
                ai_probability, classification, confidence_score = (
                    self._heuristic_classify(perplexity_score, burstiness_score)
                )
        else:
            ai_probability, classification, confidence_score = (
                self._heuristic_classify(perplexity_score, burstiness_score)
            )
            explanation = (
                "Set ANTHROPIC_API_KEY in .env to enable Claude-powered classification."
            )

        risk_level = self._risk_level(ai_probability)

        summary = self._build_ai_summary(
            text,
            classification,
            confidence_score,
            ai_probability,
            perplexity_score,
            burstiness_score,
            flagged_passages,
            explanation,
        )

        return SkillResult(
            skill_name=self.name,
            query=query,
            success=True,
            results=[
                {
                    "sentence": s,
                    "flagged": s in flagged_passages,
                }
                for s in sentences[:20]
            ],
            summary=summary,
            error="; ".join(errors) if errors else "",
            metadata={
                "mode": "ai_detection",
                "ai_probability": ai_probability,
                "classification": classification,
                "confidence_score": confidence_score,
                "perplexity_score": round(perplexity_score, 4),
                "burstiness_score": round(burstiness_score, 4),
                "similarity_score": 0.0,
                "matched_sources": [],
                "flagged_passages": flagged_passages,
                "risk_level": risk_level,
                "word_count": word_count,
            },
        )

    # ── PROJ-185: Plagiarism Scanner pipeline ─────────────────
    def _run_plagiarism(
        self, query: str, text: str, word_count: int
    ) -> SkillResult:
        """Scan text for plagiarism using DuckDuckGo Instant Answer API."""
        errors = []

        sentences = self._split_sentences(text)
        sample_phrases = self._select_sample_phrases(sentences, PLAGIARISM_SAMPLE_COUNT)

        matched_sources: list[dict] = []
        matched_phrase_count = 0

        for phrase in sample_phrases:
            try:
                sources = self._search_duckduckgo(phrase)
                if sources:
                    matched_phrase_count += 1
                    matched_sources.extend(sources)
            except Exception as exc:
                errors.append(f"DDG search: {exc}")

        # Deduplicate sources by URL
        seen_urls: set[str] = set()
        unique_sources: list[dict] = []
        for src in matched_sources:
            url = src.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_sources.append(src)

        similarity_score = matched_phrase_count / max(len(sample_phrases), 1)
        unique_content_pct = round((1.0 - similarity_score) * 100, 1)
        risk_level = self._risk_level(similarity_score)

        summary = self._build_plagiarism_summary(
            similarity_score, unique_sources, unique_content_pct
        )

        return SkillResult(
            skill_name=self.name,
            query=query,
            success=True,
            results=unique_sources,
            summary=summary,
            error="; ".join(errors) if errors else "",
            metadata={
                "mode": "plagiarism",
                "ai_probability": 0.0,
                "classification": "",
                "confidence_score": 0.0,
                "perplexity_score": 0.0,
                "burstiness_score": 0.0,
                "similarity_score": round(similarity_score, 4),
                "matched_sources": unique_sources,
                "flagged_passages": [],
                "risk_level": risk_level,
                "word_count": word_count,
                "unique_content_pct": unique_content_pct,
                "phrases_checked": len(sample_phrases),
                "phrases_matched": matched_phrase_count,
            },
        )

    # ── PROJ-186: Full Integrity Report pipeline ───────────────
    def _run_full_report(
        self, query: str, text: str, word_count: int
    ) -> SkillResult:
        """Run both AI detection and plagiarism scan, then combine into a
        structured markdown integrity report."""
        errors = []

        # ── AI detection ──────────────────────────────────────
        sentences = self._split_sentences(text)
        perplexity_score = self._calc_perplexity(text)
        burstiness_score = self._calc_burstiness(sentences)

        classification = "Uncertain"
        confidence_score = 0.5
        ai_probability = 0.5
        flagged_passages: list[str] = []
        explanation = ""

        client = self._get_claude()
        if client:
            try:
                claude_result = self._classify_with_claude(
                    text, perplexity_score, burstiness_score, sentences
                )
                classification = claude_result["classification"]
                confidence_score = claude_result["confidence_score"]
                ai_probability = claude_result["ai_probability"]
                flagged_passages = claude_result["flagged_passages"]
                explanation = claude_result["explanation"]
            except Exception as exc:
                errors.append(f"Claude classification: {exc}")
                ai_probability, classification, confidence_score = (
                    self._heuristic_classify(perplexity_score, burstiness_score)
                )
        else:
            ai_probability, classification, confidence_score = (
                self._heuristic_classify(perplexity_score, burstiness_score)
            )

        # ── Plagiarism scan ───────────────────────────────────
        sample_phrases = self._select_sample_phrases(sentences, PLAGIARISM_SAMPLE_COUNT)
        matched_sources: list[dict] = []
        matched_phrase_count = 0

        for phrase in sample_phrases:
            try:
                sources = self._search_duckduckgo(phrase)
                if sources:
                    matched_phrase_count += 1
                    matched_sources.extend(sources)
            except Exception as exc:
                errors.append(f"DDG search: {exc}")

        seen_urls: set[str] = set()
        unique_sources: list[dict] = []
        for src in matched_sources:
            url = src.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_sources.append(src)

        similarity_score = matched_phrase_count / max(len(sample_phrases), 1)
        unique_content_pct = round((1.0 - similarity_score) * 100, 1)

        # ── Combine into overall risk ─────────────────────────
        overall_risk_score = round((ai_probability + similarity_score) / 2, 4)
        risk_level = self._risk_level(overall_risk_score)

        summary = self._build_full_report(
            text=text,
            word_count=word_count,
            classification=classification,
            confidence_score=confidence_score,
            ai_probability=ai_probability,
            perplexity_score=perplexity_score,
            burstiness_score=burstiness_score,
            flagged_passages=flagged_passages,
            explanation=explanation,
            similarity_score=similarity_score,
            unique_content_pct=unique_content_pct,
            matched_sources=unique_sources,
            overall_risk_score=overall_risk_score,
            risk_level=risk_level,
        )

        return SkillResult(
            skill_name=self.name,
            query=query,
            success=True,
            results=unique_sources,
            summary=summary,
            error="; ".join(errors) if errors else "",
            metadata={
                "mode": "full_report",
                "ai_probability": ai_probability,
                "classification": classification,
                "confidence_score": confidence_score,
                "perplexity_score": round(perplexity_score, 4),
                "burstiness_score": round(burstiness_score, 4),
                "similarity_score": round(similarity_score, 4),
                "matched_sources": unique_sources,
                "flagged_passages": flagged_passages,
                "risk_level": risk_level,
                "word_count": word_count,
                "unique_content_pct": unique_content_pct,
                "overall_risk_score": overall_risk_score,
            },
        )

    # ── Statistical helpers ───────────────────────────────────

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences using regex (pure-Python fallback that
        does not require nltk)."""
        # Split on sentence-ending punctuation followed by whitespace or end-of-string
        raw = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s.strip() for s in raw if len(s.strip()) > 5]

    def _tokenize(self, text: str) -> list[str]:
        """Return lowercase word tokens, stripping punctuation."""
        return re.findall(r"\b[a-z']+\b", text.lower())

    def _calc_perplexity(self, text: str) -> float:
        """Estimate text perplexity using a unigram character-level model.

        Lower perplexity values suggest more predictable (AI-like) text.
        Uses log2-based entropy of character bigrams as a lightweight proxy
        that does not require a language model or external corpus.

        Returns a score in [0.0, 1.0] where 0.0 is maximally predictable.
        """
        if not text:
            return 0.5

        # Character bigram frequencies
        bigrams = [text[i:i+2] for i in range(len(text) - 1)]
        if not bigrams:
            return 0.5

        total = len(bigrams)
        counts = Counter(bigrams)
        probs = [c / total for c in counts.values()]

        # Shannon entropy of the bigram distribution
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)

        # Normalise to [0, 1] — max entropy for bigrams over printable ASCII
        # is ~log2(95^2) ≈ 13.2 bits; typical English prose sits ~8-10 bits.
        normalised = min(entropy / 13.2, 1.0)

        # Invert: high entropy (varied) → low perplexity score → more human-like
        return round(1.0 - normalised, 4)

    def _calc_burstiness(self, sentences: list[str]) -> float:
        """Calculate burstiness as the coefficient of variation (CV) of
        sentence lengths.

        AI-generated text tends to have uniform sentence lengths (low CV),
        while human writing has more variation (high CV).

        Returns a score in [0.0, 1.0] where 1.0 = highly uniform (AI-like).
        """
        if len(sentences) < 2:
            return 0.5

        lengths = [len(s.split()) for s in sentences]
        mean = sum(lengths) / len(lengths)
        if mean == 0:
            return 0.5

        variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
        std_dev = math.sqrt(variance)
        cv = std_dev / mean  # coefficient of variation

        # Clamp: cv > 1.0 is very bursty human text; cv < 0.2 is very uniform
        # We invert so 1.0 = uniform (AI-like)
        normalised_uniformity = max(0.0, 1.0 - min(cv, 1.5) / 1.5)
        return round(normalised_uniformity, 4)

    def _heuristic_classify(
        self, perplexity_score: float, burstiness_score: float
    ) -> tuple[float, str, float]:
        """Fallback heuristic classifier when Claude is unavailable.

        Returns (ai_probability, classification, confidence_score).
        """
        # Both high → strongly AI-like
        ai_probability = (perplexity_score + burstiness_score) / 2

        if ai_probability >= 0.70:
            classification = "AI-generated"
            confidence_score = min(ai_probability + 0.10, 1.0)
        elif ai_probability <= 0.35:
            classification = "Human-written"
            confidence_score = max(1.0 - ai_probability - 0.10, 0.0)
        else:
            classification = "Uncertain"
            confidence_score = 0.5

        return round(ai_probability, 4), classification, round(confidence_score, 4)

    # ── Claude classification (PROJ-184) ──────────────────────
    def _classify_with_claude(
        self,
        text: str,
        perplexity_score: float,
        burstiness_score: float,
        sentences: list[str],
    ) -> dict:
        """Use Claude (Haiku) to classify the text and identify suspicious passages.

        Returns a dict with: classification, confidence_score, ai_probability,
        flagged_passages, explanation.
        """
        client = self._get_claude()
        if not client:
            raise RuntimeError("Claude client not initialised.")

        sample = text[:3000]  # cap to avoid large token bills
        sentence_list = "\n".join(f"- {s}" for s in sentences[:30])

        prompt = f"""You are an academic integrity expert specialising in detecting AI-generated text.

Analyse the following text and classify it. You have been provided with two statistical signals:
- Perplexity score: {perplexity_score:.3f} (0 = very predictable/AI-like, 1 = very varied/human-like)
- Burstiness score: {burstiness_score:.3f} (0 = varied sentence lengths/human-like, 1 = uniform lengths/AI-like)

Text to analyse (first 3000 characters):
\"\"\"
{sample}
\"\"\"

Sentence breakdown:
{sentence_list}

Respond with ONLY valid JSON in exactly this schema (no markdown, no extra keys):
{{
  "classification": "AI-generated" | "Human-written" | "Uncertain",
  "ai_probability": <float 0.0-1.0>,
  "confidence_score": <float 0.0-1.0>,
  "flagged_passages": [<up to 5 verbatim suspicious sentences from the text>],
  "explanation": "<2-3 sentence explanation of the classification reasoning>"
}}"""

        message = client.messages.create(
            model=CLAUDE_HAIKU_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        import json
        parsed = json.loads(raw)

        return {
            "classification": parsed.get("classification", "Uncertain"),
            "confidence_score": float(parsed.get("confidence_score", 0.5)),
            "ai_probability": float(parsed.get("ai_probability", 0.5)),
            "flagged_passages": parsed.get("flagged_passages", []),
            "explanation": parsed.get("explanation", ""),
        }

    # ── DuckDuckGo plagiarism search (PROJ-185) ───────────────
    def _select_sample_phrases(
        self, sentences: list[str], n: int
    ) -> list[str]:
        """Pick n evenly-spaced sentences of at least 8 words for searching."""
        candidates = [s for s in sentences if len(s.split()) >= 8]
        if not candidates:
            return sentences[:n]
        if len(candidates) <= n:
            return candidates

        step = len(candidates) / n
        return [candidates[int(i * step)] for i in range(n)]

    def _search_duckduckgo(self, phrase: str) -> list[dict]:
        """Query the DuckDuckGo Instant Answer API for a phrase.

        Returns a list of matched source dicts: {url, title, matched_text}.
        """
        # Use the first 10 words of the phrase to stay within URL limits
        search_query = " ".join(phrase.split()[:10])

        params = {
            "q": f'"{search_query}"',
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }

        resp = self._retry_get(DUCKDUCKGO_API_URL, params=params)
        data = resp.json()

        sources: list[dict] = []

        # AbstractURL is the primary result
        if data.get("AbstractURL") and data.get("Abstract"):
            sources.append({
                "url": data["AbstractURL"],
                "title": data.get("Heading", ""),
                "matched_text": phrase,
            })

        # RelatedTopics may also carry URLs
        for topic in data.get("RelatedTopics", [])[:3]:
            if isinstance(topic, dict) and topic.get("FirstURL"):
                sources.append({
                    "url": topic["FirstURL"],
                    "title": topic.get("Text", "")[:120],
                    "matched_text": phrase,
                })

        return sources

    # ── Risk classification ───────────────────────────────────
    def _risk_level(self, score: float) -> str:
        """Map a 0.0-1.0 risk score to 'low', 'medium', or 'high'."""
        if score >= 0.65:
            return "high"
        if score >= 0.35:
            return "medium"
        return "low"

    # ── Summary builders ──────────────────────────────────────

    def _build_ai_summary(
        self,
        text: str,
        classification: str,
        confidence_score: float,
        ai_probability: float,
        perplexity_score: float,
        burstiness_score: float,
        flagged_passages: list[str],
        explanation: str,
    ) -> str:
        pct = int(ai_probability * 100)
        conf = int(confidence_score * 100)
        lines = [
            f"## AI Content Detection Report",
            f"",
            f"**Classification:** {classification}  ",
            f"**AI Probability:** {pct}%  ",
            f"**Confidence:** {conf}%  ",
            f"",
            f"### Statistical Signals",
            f"| Signal | Score | Interpretation |",
            f"|--------|-------|----------------|",
            f"| Perplexity | {perplexity_score:.3f} | "
            f"{'Predictable (AI-like)' if perplexity_score > 0.6 else 'Varied (Human-like)'} |",
            f"| Burstiness | {burstiness_score:.3f} | "
            f"{'Uniform sentences (AI-like)' if burstiness_score > 0.6 else 'Varied lengths (Human-like)'} |",
        ]

        if explanation:
            lines += ["", "### Explanation", explanation]

        if flagged_passages:
            lines += ["", "### Flagged Passages"]
            for i, passage in enumerate(flagged_passages[:5], 1):
                lines.append(f"{i}. *\"{passage}\"*")

        return "\n".join(lines)

    def _build_plagiarism_summary(
        self,
        similarity_score: float,
        matched_sources: list[dict],
        unique_content_pct: float,
    ) -> str:
        sim_pct = int(similarity_score * 100)
        lines = [
            f"## Plagiarism Scan Report",
            f"",
            f"**Similarity Score:** {sim_pct}%  ",
            f"**Unique Content:** {unique_content_pct}%  ",
        ]

        if matched_sources:
            lines += ["", "### Matched Sources"]
            for src in matched_sources[:10]:
                title = src.get("title", "Unknown")
                url = src.get("url", "")
                matched = src.get("matched_text", "")[:80]
                lines.append(f"- **{title}** — {url}")
                if matched:
                    lines.append(f"  *Matched phrase:* \"{matched}...\"")
        else:
            lines += ["", "No matching web sources found. Content appears original."]

        return "\n".join(lines)

    def _build_full_report(
        self,
        text: str,
        word_count: int,
        classification: str,
        confidence_score: float,
        ai_probability: float,
        perplexity_score: float,
        burstiness_score: float,
        flagged_passages: list[str],
        explanation: str,
        similarity_score: float,
        unique_content_pct: float,
        matched_sources: list[dict],
        overall_risk_score: float,
        risk_level: str,
    ) -> str:
        ai_pct = int(ai_probability * 100)
        sim_pct = int(similarity_score * 100)
        risk_pct = int(overall_risk_score * 100)

        risk_emoji = {"low": "✅", "medium": "⚠️", "high": "🚨"}.get(risk_level, "")

        if risk_level == "high":
            recommendation = (
                "HIGH RISK — this submission shows strong indicators of AI-generated "
                "content and/or significant similarity to online sources. Further "
                "review or conversation with the student is strongly recommended."
            )
        elif risk_level == "medium":
            recommendation = (
                "MEDIUM RISK — some indicators of AI-generated content or online "
                "similarity were detected. Manual review of the flagged passages is "
                "advised before any academic judgement."
            )
        else:
            recommendation = (
                "LOW RISK — no significant indicators of AI-generated content or "
                "plagiarism detected. The submission appears original."
            )

        lines = [
            "# Academic Integrity Report",
            "",
            f"**Overall Risk Score:** {risk_pct}% {risk_emoji}  ",
            f"**Risk Level:** {risk_level.upper()}  ",
            f"**Word Count Analysed:** {word_count}  ",
            "",
            "---",
            "",
            "## 1. AI Content Detection (PROJ-184)",
            "",
            f"| Metric | Result |",
            f"|--------|--------|",
            f"| Classification | {classification} |",
            f"| AI Probability | {ai_pct}% |",
            f"| Confidence | {int(confidence_score * 100)}% |",
            f"| Perplexity Score | {perplexity_score:.3f} |",
            f"| Burstiness Score | {burstiness_score:.3f} |",
        ]

        if explanation:
            lines += ["", f"**Analysis:** {explanation}"]

        if flagged_passages:
            lines += ["", "**Flagged Passages:**"]
            for i, passage in enumerate(flagged_passages[:5], 1):
                lines.append(f"{i}. *\"{passage}\"*")

        lines += [
            "",
            "---",
            "",
            "## 2. Plagiarism Scan (PROJ-185)",
            "",
            f"| Metric | Result |",
            f"|--------|--------|",
            f"| Similarity Score | {sim_pct}% |",
            f"| Unique Content | {unique_content_pct}% |",
            f"| Sources Matched | {len(matched_sources)} |",
        ]

        if matched_sources:
            lines += ["", "**Matched Sources:**"]
            for src in matched_sources[:5]:
                title = src.get("title", "Unknown")
                url = src.get("url", "")
                lines.append(f"- {title} — {url}")
        else:
            lines.append("")
            lines.append("No matching web sources found.")

        lines += [
            "",
            "---",
            "",
            "## 3. Recommendation",
            "",
            recommendation,
        ]

        return "\n".join(lines)
