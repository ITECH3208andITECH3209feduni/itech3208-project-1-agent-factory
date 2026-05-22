# tests/test_sprint2_skills.py
# ──────────────────────────────────────────────────────────────
# Test suite for Sprint 2 skills — PROJ-193
#
# Covers:
#   PROJ-184  AcademicIntegritySkill — AI detection
#   PROJ-185  AcademicIntegritySkill — plagiarism scan
#   PROJ-186  AcademicIntegritySkill — full report
#   PROJ-187  AmazonSellerSkill      — Alibaba supplier finder
#   PROJ-188  AmazonSellerSkill      — PPC campaign builder
#   PROJ-189  AmazonSellerSkill      — Product progress analysis
#   PROJ-190  AmazonSellerSkill      — Profit optimiser
#   PROJ-191  ExportSkill            — PDF + Excel export
# ──────────────────────────────────────────────────────────────

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

# Skip Claude-dependent tests when no API key is available
_HAS_API_KEY = (
    os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE") != "YOUR_API_KEY_HERE"
    and bool(os.environ.get("ANTHROPIC_API_KEY"))
)
requires_claude = pytest.mark.skipif(
    not _HAS_API_KEY,
    reason="ANTHROPIC_API_KEY not set — skipping Claude-dependent test"
)

from skills.base_skill import SkillResult
from skills.academic_integrity import AcademicIntegritySkill
from skills.amazon_seller import AmazonSellerSkill
from skills.export import ExportSkill, export_to_pdf, export_to_excel
from components.integrity_cards import IntegrityCard
from components.seller_cards import SupplierCard, CampaignCard


# ── Fixtures ───────────────────────────────────────────────────

SAMPLE_TEXT_AI = (
    "Artificial intelligence represents a significant paradigm shift in computational "
    "methodology. The systematic application of machine learning algorithms enables "
    "automated decision-making processes across diverse domains. Natural language "
    "processing facilitates the interpretation of human communication patterns. "
    "Furthermore, deep learning architectures demonstrate superior performance on "
    "complex pattern recognition tasks. These technological advancements continue to "
    "reshape our understanding of intelligent systems and their potential applications."
)  # 75 words — above MIN_WORD_COUNT threshold

SAMPLE_TEXT_SHORT = "This is too short."

SAMPLE_QUERY_INTEGRITY_AI       = f"detect ai: {SAMPLE_TEXT_AI}"
SAMPLE_QUERY_INTEGRITY_PLAGIARISM = f"plagiarism check: {SAMPLE_TEXT_AI}"
SAMPLE_QUERY_INTEGRITY_FULL     = f"integrity report: {SAMPLE_TEXT_AI}"

SAMPLE_QUERY_SUPPLIER  = "find alibaba suppliers for: wireless earbuds"
SAMPLE_QUERY_PPC       = "build ppc campaign for: bamboo toothbrushes"
SAMPLE_QUERY_PROGRESS  = "analyze product progress: wireless earbuds B07XYZ123"
SAMPLE_QUERY_PROFIT    = "optimize profit: selling_price=24.99 cost_price=7.00 fees=15 ads=10"


# ── Academic Integrity Skill tests (PROJ-184, 185, 186) ────────

class TestAcademicIntegritySkill:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.skill = AcademicIntegritySkill()

    def test_skill_name(self):
        assert self.skill.name == "academic_integrity"

    def test_skill_has_triggers(self):
        assert len(self.skill.triggers) > 0

    def test_returns_skill_result(self):
        result = self.skill(SAMPLE_QUERY_INTEGRITY_AI)
        assert isinstance(result, SkillResult)
        assert result.skill_name == "academic_integrity"

    def test_short_text_returns_error(self):
        result = self.skill(f"detect ai: {SAMPLE_TEXT_SHORT}")
        assert not result.success
        assert "50 words" in result.error.lower() or "word" in result.error.lower()

    def test_ai_detection_mode(self):
        result = self.skill(SAMPLE_QUERY_INTEGRITY_AI)
        meta = result.metadata
        assert meta.get("mode") == "ai_detection"
        assert "ai_probability" in meta
        assert 0.0 <= meta["ai_probability"] <= 1.0
        assert "classification" in meta
        assert meta["classification"] in ("AI-generated", "Human-written", "Uncertain")
        assert "perplexity_score" in meta
        assert "burstiness_score" in meta

    @requires_claude
    def test_plagiarism_mode(self):
        result = self.skill(SAMPLE_QUERY_INTEGRITY_PLAGIARISM)
        meta = result.metadata
        assert meta.get("mode") == "plagiarism"
        assert "similarity_score" in meta
        assert 0.0 <= meta["similarity_score"] <= 1.0
        assert "matched_sources" in meta
        assert isinstance(meta["matched_sources"], list)

    @requires_claude
    def test_full_report_mode(self):
        result = self.skill(SAMPLE_QUERY_INTEGRITY_FULL)
        meta = result.metadata
        assert meta.get("mode") == "full_report"
        assert "ai_probability" in meta
        assert "similarity_score" in meta
        # Summary should contain a markdown report
        assert len(result.summary) > 50

    def test_word_count_populated(self):
        result = self.skill(SAMPLE_QUERY_INTEGRITY_AI)
        assert result.metadata.get("word_count", 0) >= 50

    def test_risk_level_valid(self):
        result = self.skill(SAMPLE_QUERY_INTEGRITY_AI)
        assert result.metadata.get("risk_level") in ("low", "medium", "high")

    def test_duration_recorded(self):
        result = self.skill(SAMPLE_QUERY_INTEGRITY_AI)
        assert result.duration_sec > 0.0


# ── IntegrityCard tests ────────────────────────────────────────

class TestIntegrityCard:

    def _make_raw(self, **overrides):
        base = {
            "classification": "AI-generated",
            "ai_probability": 0.85,
            "confidence_score": 0.90,
            "risk_level": "high",
            "flagged_count": 3,
            "similarity_score": 0.12,
            "word_count": 75,
            "explanation": "High perplexity uniformity detected.",
        }
        base.update(overrides)
        return base

    def test_from_skill_result(self):
        card = IntegrityCard.from_skill_result(self._make_raw())
        assert card.classification == "AI-generated"
        assert card.ai_probability == pytest.approx(0.85)

    def test_risk_color_high(self):
        card = IntegrityCard.from_skill_result(self._make_raw(risk_level="high"))
        assert card.risk_color == "red"

    def test_risk_color_medium(self):
        card = IntegrityCard.from_skill_result(self._make_raw(risk_level="medium"))
        assert card.risk_color == "yellow"

    def test_risk_color_low(self):
        card = IntegrityCard.from_skill_result(self._make_raw(risk_level="low"))
        assert card.risk_color == "green"

    def test_to_dict_contains_all_fields(self):
        card = IntegrityCard.from_skill_result(self._make_raw())
        d = card.to_dict()
        for field in ("classification", "ai_probability", "risk_level", "risk_color"):
            assert field in d


# ── Amazon Seller Skill tests (PROJ-187, 188, 189, 190) ────────

class TestAmazonSellerSkill:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.skill = AmazonSellerSkill()

    def test_skill_name(self):
        assert self.skill.name == "amazon_seller"

    def test_returns_skill_result(self):
        result = self.skill(SAMPLE_QUERY_SUPPLIER)
        assert isinstance(result, SkillResult)

    def test_supplier_mode_detected(self):
        result = self.skill(SAMPLE_QUERY_SUPPLIER)
        assert result.metadata.get("mode") == "supplier_finder"

    def test_supplier_returns_results(self):
        result = self.skill(SAMPLE_QUERY_SUPPLIER)
        assert len(result.results) > 0

    def test_supplier_result_has_required_fields(self):
        result = self.skill(SAMPLE_QUERY_SUPPLIER)
        if result.results:
            r = result.results[0]
            for field in ("supplier_name", "product_title", "price_range", "url"):
                assert field in r, f"Missing field: {field}"
            # MOQ may be stored as 'moq' or 'min_order_qty'
            assert "moq" in r or "min_order_qty" in r, "Missing MOQ field"

    @requires_claude
    def test_ppc_mode_detected(self):
        result = self.skill(SAMPLE_QUERY_PPC)
        assert result.metadata.get("mode") == "ppc_builder"

    @requires_claude
    def test_ppc_returns_keywords(self):
        result = self.skill(SAMPLE_QUERY_PPC)
        assert len(result.results) > 0
        if result.results:
            r = result.results[0]
            assert "keyword" in r

    @requires_claude
    def test_progress_mode_detected(self):
        result = self.skill(SAMPLE_QUERY_PROGRESS)
        assert result.metadata.get("mode") == "progress_analysis"

    @requires_claude
    def test_profit_mode_detected(self):
        result = self.skill(SAMPLE_QUERY_PROFIT)
        assert result.metadata.get("mode") == "profit_optimiser"

    @requires_claude
    def test_profit_computes_margins(self):
        result = self.skill(SAMPLE_QUERY_PROFIT)
        meta = result.metadata
        assert "gross_margin" in meta or "current_metrics" in meta

    def test_duration_recorded(self):
        result = self.skill(SAMPLE_QUERY_SUPPLIER)
        assert result.duration_sec > 0.0


# ── SupplierCard / CampaignCard tests ──────────────────────────

class TestSellerCards:

    def test_supplier_card_from_skill_result(self):
        raw = {
            "supplier_name": "Shenzhen Electronics Co",
            "product_title": "Wireless Earbuds TWS",
            "price_range": "$3.50 - $7.00",
            "moq": "500",
            "rating": "4.8",
            "verified": True,
            "trade_assurance": True,
            "url": "https://www.alibaba.com/product/123",
        }
        card = SupplierCard.from_skill_result(raw)
        assert card.supplier_name == "Shenzhen Electronics Co"
        d = card.to_dict()
        assert "supplier_name" in d
        assert "price_range" in d

    def test_campaign_card_from_skill_result(self):
        raw = {
            "keyword": "wireless earbuds",
            "match_type": "Broad",
            "suggested_bid": 0.75,
            "estimated_clicks": 120,
        }
        card = CampaignCard.from_skill_result(raw)
        assert card.keyword == "wireless earbuds"
        assert card.match_type == "Broad"
        d = card.to_dict()
        assert "keyword" in d
        assert "suggested_bid" in d

    def test_campaign_card_match_colour(self):
        for match_type in ("Broad", "Phrase", "Exact"):
            raw = {"keyword": "test", "match_type": match_type, "suggested_bid": 0.5, "estimated_clicks": 50}
            card = CampaignCard.from_skill_result(raw)
            colour = card.match_colour()
            assert colour.startswith("#")


# ── Export Skill tests (PROJ-191) ──────────────────────────────

SAMPLE_EXPORT_DATA = {
    "skill": "literature",
    "query": "machine learning",
    "success": True,
    "results": [
        {"title": "Deep Learning", "authors": "LeCun et al.", "year": "2015",
         "abstract": "A review of deep learning.", "source": "arXiv", "url": "https://arxiv.org/1", "citations": 5000},
        {"title": "BERT", "authors": "Devlin et al.", "year": "2018",
         "abstract": "Pre-training of transformers.", "source": "arXiv", "url": "https://arxiv.org/2", "citations": 3000},
    ],
    "summary": "Foundational deep learning and NLP papers.",
    "error": "",
    "metadata": {"quick_synthesis": "Great papers."},
    "duration": "1.23s",
}


class TestExportSkill:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.skill = ExportSkill()

    def test_skill_name(self):
        assert self.skill.name == "export"

    def test_export_to_pdf_creates_file(self):
        path = export_to_pdf(SAMPLE_EXPORT_DATA)
        assert os.path.exists(path)
        assert path.endswith(".pdf") or path.endswith(".txt")
        os.remove(path)

    def test_export_to_excel_creates_file(self):
        path = export_to_excel(SAMPLE_EXPORT_DATA)
        assert os.path.exists(path)
        assert path.endswith(".xlsx") or path.endswith(".csv")
        os.remove(path)

    def test_export_to_pdf_custom_filename(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp = f.name
        try:
            path = export_to_pdf(SAMPLE_EXPORT_DATA, filename=tmp)
            assert os.path.exists(path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def test_export_skill_run_no_data(self):
        result = self.skill("export pdf")
        assert isinstance(result, SkillResult)
        # Should return instructions or succeed with guidance
        assert result.skill_name == "export"

    def test_export_skill_run_with_pdf(self):
        query = f"export pdf: {json.dumps(SAMPLE_EXPORT_DATA)}"
        result = self.skill(query)
        assert isinstance(result, SkillResult)
        # Clean up file if created
        if result.success and result.metadata.get("file_path"):
            path = result.metadata["file_path"]
            if os.path.exists(path):
                os.remove(path)

    def test_export_skill_run_with_excel(self):
        query = f"export excel: {json.dumps(SAMPLE_EXPORT_DATA)}"
        result = self.skill(query)
        assert isinstance(result, SkillResult)
        if result.success and result.metadata.get("file_path"):
            path = result.metadata["file_path"]
            if os.path.exists(path):
                os.remove(path)


# ── Orchestrator routing tests ─────────────────────────────────

class TestOrchestratorRouting:
    """Test that the updated orchestrator quick-routes to new skills."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from agent.orchestrator import Orchestrator
        self.orch = Orchestrator()

    def test_routes_plagiarism_to_integrity(self):
        route = self.orch._quick_route("plagiarism check this essay")
        assert route == "integrity"

    def test_routes_ai_detection_to_integrity(self):
        route = self.orch._quick_route("detect ai in this text")
        assert route == "integrity"

    def test_routes_alibaba_to_seller(self):
        route = self.orch._quick_route("find alibaba supplier for earbuds")
        assert route == "seller"

    def test_routes_ppc_to_seller(self):
        route = self.orch._quick_route("build ppc campaign for my product")
        assert route == "seller"

    def test_routes_profit_to_seller(self):
        route = self.orch._quick_route("optimize profit margin for amazon")
        assert route == "seller"

    def test_routes_amazon_product(self):
        route = self.orch._quick_route("best wireless earbuds to buy on amazon")
        assert route == "amazon"

    def test_routes_literature(self):
        route = self.orch._quick_route("find arxiv papers on neural networks")
        assert route == "literature"
