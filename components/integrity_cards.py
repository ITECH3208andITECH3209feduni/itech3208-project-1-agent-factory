# components/integrity_cards.py
# ──────────────────────────────────────────────────────────────
# IntegrityCard dataclass — typed academic integrity result for
# Web UI rendering (PROJ-184, PROJ-185, PROJ-186)
# ──────────────────────────────────────────────────────────────

from dataclasses import dataclass, field


@dataclass
class IntegrityCard:
    """Typed representation of a single academic integrity analysis result.

    Fields mirror the ``metadata`` dict returned by ``AcademicIntegritySkill``
    so that the Web UI can render risk indicators, scores, and flags without
    parsing raw SkillResult dicts.
    """

    # ── Classification ────────────────────────────────────────
    classification:  str   = "Uncertain"
    """AI-generated | Human-written | Uncertain"""

    ai_probability:  float = 0.0
    """Probability [0.0, 1.0] that the text was AI-generated."""

    confidence_score: float = 0.0
    """How confident the detector is in the classification [0.0, 1.0]."""

    # ── Risk ──────────────────────────────────────────────────
    risk_level:      str   = "low"
    """Overall risk level: 'low' | 'medium' | 'high'."""

    # ── Passages ──────────────────────────────────────────────
    flagged_count:   int   = 0
    """Number of passages flagged as suspicious."""

    # ── Plagiarism ────────────────────────────────────────────
    similarity_score: float = 0.0
    """Fraction [0.0, 1.0] of sample phrases found on the web."""

    # ── Meta ──────────────────────────────────────────────────
    word_count:      int   = 0
    """Number of words in the analysed text."""

    explanation:     str   = ""
    """Human-readable explanation of the classification."""

    # ── Optional extras stored verbatim from metadata ─────────
    perplexity_score:  float      = 0.0
    burstiness_score:  float      = 0.0
    matched_sources:   list       = field(default_factory=list)
    flagged_passages:  list       = field(default_factory=list)
    mode:              str        = "ai_detection"

    # ── Derived properties ────────────────────────────────────
    @property
    def risk_color(self) -> str:
        """Return a CSS-friendly colour string based on risk level.

        - ``'red'``    — high risk
        - ``'yellow'`` — medium risk
        - ``'green'``  — low risk
        """
        return {"high": "red", "medium": "yellow", "low": "green"}.get(
            self.risk_level, "green"
        )

    @property
    def ai_probability_pct(self) -> int:
        """AI probability as a rounded integer percentage."""
        return round(self.ai_probability * 100)

    @property
    def similarity_pct(self) -> int:
        """Similarity score as a rounded integer percentage."""
        return round(self.similarity_score * 100)

    @property
    def confidence_pct(self) -> int:
        """Confidence score as a rounded integer percentage."""
        return round(self.confidence_score * 100)

    # ── Serialisation ─────────────────────────────────────────
    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict of all card fields."""
        return {
            "classification":   self.classification,
            "ai_probability":   self.ai_probability,
            "ai_probability_pct": self.ai_probability_pct,
            "confidence_score": self.confidence_score,
            "confidence_pct":   self.confidence_pct,
            "risk_level":       self.risk_level,
            "risk_color":       self.risk_color,
            "flagged_count":    self.flagged_count,
            "similarity_score": self.similarity_score,
            "similarity_pct":   self.similarity_pct,
            "word_count":       self.word_count,
            "explanation":      self.explanation,
            "perplexity_score": self.perplexity_score,
            "burstiness_score": self.burstiness_score,
            "matched_sources":  self.matched_sources,
            "flagged_passages": self.flagged_passages,
            "mode":             self.mode,
        }

    # ── Factory ───────────────────────────────────────────────
    @classmethod
    def from_skill_result(cls, raw: dict) -> "IntegrityCard":
        """Build an IntegrityCard from the ``metadata`` dict (or a full
        ``SkillResult.to_dict()`` output) returned by ``AcademicIntegritySkill``.

        Accepts either the raw ``metadata`` sub-dict or a full skill result
        dict — ``metadata`` is extracted automatically if present.

        Example::

            result = skill(query)
            card = IntegrityCard.from_skill_result(result.to_dict())
        """
        # Unwrap full SkillResult dict if needed
        meta: dict = raw.get("metadata", raw)

        flagged_passages = meta.get("flagged_passages", [])

        return cls(
            classification   = meta.get("classification", "Uncertain"),
            ai_probability   = float(meta.get("ai_probability", 0.0)),
            confidence_score = float(meta.get("confidence_score", 0.0)),
            risk_level       = meta.get("risk_level", "low"),
            flagged_count    = len(flagged_passages),
            similarity_score = float(meta.get("similarity_score", 0.0)),
            word_count       = int(meta.get("word_count", 0)),
            explanation      = meta.get("explanation", ""),
            perplexity_score = float(meta.get("perplexity_score", 0.0)),
            burstiness_score = float(meta.get("burstiness_score", 0.0)),
            matched_sources  = list(meta.get("matched_sources", [])),
            flagged_passages = list(flagged_passages),
            mode             = meta.get("mode", "ai_detection"),
        )
