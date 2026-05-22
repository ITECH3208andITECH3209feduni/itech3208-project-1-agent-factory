# skills/amazon_seller.py
# ──────────────────────────────────────────────────────────────
# Amazon Seller Intelligence Skill
#
# PROJ-187: Alibaba Supplier Finder
#   Scrapes Alibaba trade search for verified suppliers;
#   falls back to realistic mock data if scraping fails.
#
# PROJ-188: PPC Campaign Builder
#   Uses Claude to generate a full Sponsored Products campaign
#   structure with keywords, bids, budgets, and ACOS targets.
#
# PROJ-189: Product Progress Analysis
#   Uses Claude to estimate BSR trend, review velocity,
#   pricing history, Buy Box status, saturation, and growth.
#
# PROJ-190: Profit Optimiser
#   Parses cost/price/fee inputs from the query, computes
#   margin/ROI metrics, and uses Claude for improvement recs.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import re
import time
import random
from typing import Any
from urllib.parse import quote_plus

import requests

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from skills.base_skill import BaseSkill, SkillResult
from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, REQUEST_TIMEOUT

# ── Query mode trigger sets ────────────────────────────────────
_SUPPLIER_TRIGGERS = {
    "alibaba", "supplier", "wholesale", "manufacturer",
    "source product", "find supplier", "china supplier", "bulk",
}
_PPC_TRIGGERS = {
    "ppc", "sponsored", "campaign", "keywords", "ads",
    "advertising", "acos", "keyword research",
}
_PROGRESS_TRIGGERS = {
    "progress", "trend", "bsr trend", "review velocity",
    "market analysis", "product analysis", "growth",
}
_PROFIT_TRIGGERS = {
    "profit", "margin", "optimize", "optimise", "roi",
    "fees", "cost analysis", "pricing strategy",
}

# ── Alibaba scraping constants ─────────────────────────────────
_ALIBABA_SEARCH_URL = (
    "https://www.alibaba.com/trade/search"
    "?SearchText={query}&IndexArea=product_en"
)
_ALIBABA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.alibaba.com/",
}


# ── Mock supplier data factory ─────────────────────────────────

def _mock_suppliers(product: str) -> list[dict]:
    """
    Return a list of 10 realistic-looking mock supplier records.

    Each supplier gets a unique product variant + Alibaba search URL so
    the links return relevant live results rather than a single generic page.
    All records are flagged with ``demo_data: True``.
    """
    base_names = [
        "Shenzhen TechSource Co., Ltd.",
        "Guangzhou Premier Trading Co., Ltd.",
        "Ningbo Global Supplies Ltd.",
        "Dongguan FastMake Manufacturing",
        "Zhejiang Topline Electronics Co.",
        "Foshan Horizon Industrial Co., Ltd.",
        "Hangzhou Pacific Wholesale Corp.",
        "Xiamen StarExport Trading Ltd.",
        "Suzhou BrightCraft Co., Ltd.",
        "Wuhan EastWind Manufacturing Co.",
    ]
    # Product-specific variant suffixes — each gives a unique, targeted search
    variant_suffixes = [
        "wholesale manufacturer",
        "bulk factory price",
        "OEM custom logo",
        "private label supplier",
        "low MOQ wholesale",
        "certified manufacturer",
        "export quality supplier",
        "dropship wholesale",
        "custom design factory",
        "branded bulk order",
    ]
    product_title_prefix = product.title()
    results = []
    for i, name in enumerate(base_names):
        low = round(random.uniform(1.5, 8.0), 2)
        high = round(low * random.uniform(1.5, 3.0), 2)
        variant = variant_suffixes[i % len(variant_suffixes)]
        search_term = f"{product} {variant}"
        results.append({
            "supplier_name":     name,
            "product_title":     f"{product_title_prefix} — {variant.title()}",
            "price_range":       f"${low:.2f} - ${high:.2f}",
            "min_order_qty":     str(random.choice([50, 100, 200, 500, 1000])),
            "rating":            f"{random.uniform(4.0, 5.0):.1f}",
            "verified_supplier": random.random() > 0.2,
            "trade_assurance":   random.random() > 0.3,
            "url":               (
                f"https://www.alibaba.com/trade/search?SearchText="
                f"{quote_plus(product)}&IndexArea=product_en"
            ),
            "demo_data":         True,
        })
    return results


# ── AmazonSellerSkill ──────────────────────────────────────────

class AmazonSellerSkill(BaseSkill):
    """
    Amazon Seller Intelligence skill covering four capabilities:

    * PROJ-187  Alibaba Supplier Finder
    * PROJ-188  PPC Campaign Builder
    * PROJ-189  Product Progress Analysis
    * PROJ-190  Profit Optimiser
    """

    name = "amazon_seller"
    description = (
        "Amazon seller tools: find Alibaba suppliers, build PPC campaigns, "
        "analyse product progress / BSR trends, and optimise profit margins. "
        "Use when the user asks about sourcing, wholesale, advertising, "
        "keyword research, product growth, margins, or ROI."
    )
    triggers = list(
        _SUPPLIER_TRIGGERS
        | _PPC_TRIGGERS
        | _PROGRESS_TRIGGERS
        | _PROFIT_TRIGGERS
    )

    _claude_client: anthropic.Anthropic | None = None

    # ── Claude client (lazy) ──────────────────────────────────

    @classmethod
    def _get_claude(cls) -> anthropic.Anthropic | None:
        """Return a cached Anthropic client, or None if unavailable."""
        if not ANTHROPIC_AVAILABLE:
            return None
        if cls._claude_client is None:
            try:
                cls._claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            except Exception:
                pass
        return cls._claude_client

    # ── Dispatch ──────────────────────────────────────────────

    def run(self, query: str) -> SkillResult:
        """Route the query to the appropriate sub-skill."""
        import re as _re
        # Strip key=value parameter pairs before keyword matching so that
        # "ads=3.00" doesn't accidentally trigger _PPC_TRIGGERS on "ads"
        q_stripped = _re.sub(r"\b\w+=[\d.]+", "", query).lower()

        if any(t in q_stripped for t in _SUPPLIER_TRIGGERS):
            return self._run_supplier_finder(query)

        # Check profit BEFORE PPC — "profit", "margin", "roi" are unambiguous;
        # PPC keywords ("ads", "campaign") can appear in profit queries as params
        if any(t in q_stripped for t in _PROFIT_TRIGGERS):
            return self._run_profit_optimiser(query)

        if any(t in q_stripped for t in _PPC_TRIGGERS):
            return self._run_ppc_builder(query)

        if any(t in q_stripped for t in _PROGRESS_TRIGGERS):
            return self._run_progress_analysis(query)

        return SkillResult(
            skill_name=self.name,
            query=query,
            success=False,
            error=(
                "Query did not match any seller sub-skill. "
                "Try keywords like 'supplier', 'ppc', 'progress', or 'profit'."
            ),
        )

    # ──────────────────────────────────────────────────────────
    # PROJ-187  Alibaba Supplier Finder
    # ──────────────────────────────────────────────────────────

    def _run_supplier_finder(self, query: str) -> SkillResult:
        """
        Find verified Alibaba suppliers for the product in the query.

        Parses the search subject from after a colon (e.g.
        ``"find alibaba suppliers for: wireless earbuds"``), then
        scrapes Alibaba trade search.  Falls back to demo data when
        live scraping fails.
        """
        product = self._parse_subject(query) or query.strip()

        demo_mode = False
        suppliers: list[dict] = []
        scrape_error = ""

        if BS4_AVAILABLE:
            try:
                suppliers = self._scrape_alibaba(product)
            except Exception as exc:
                scrape_error = str(exc)

        if not suppliers:
            suppliers = _mock_suppliers(product)
            demo_mode = True

        summary = self._summarise_suppliers(product, suppliers, demo_mode)

        return SkillResult(
            skill_name=self.name,
            query=query,
            success=True,
            results=suppliers,
            summary=summary,
            error=scrape_error,
            metadata={
                "mode":        "supplier_finder",
                "product":     product,
                "demo_mode":   demo_mode,
                "total_found": len(suppliers),
                "source":      "Alibaba.com" if not demo_mode else "Mock (demo data)",
            },
        )

    def _scrape_alibaba(self, product: str) -> list[dict]:
        """
        Scrape up to 10 supplier cards from Alibaba trade search.

        Raises on HTTP or parse failure so the caller can fall back
        to mock data.
        """
        url = _ALIBABA_SEARCH_URL.format(query=quote_plus(product))
        time.sleep(random.uniform(1.0, 2.0))

        resp = requests.get(url, headers=_ALIBABA_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        suppliers: list[dict] = []

        # Alibaba renders results in <div class="organic-list-offer-outter"> cards
        cards = (
            soup.select(".organic-list-offer-outter")
            or soup.select(".offer-list-row")
            or soup.select("[class*='offer']")
        )

        for card in cards[:10]:
            supplier = self._parse_alibaba_card(card, product)
            if supplier:
                suppliers.append(supplier)

        if not suppliers:
            raise ValueError(
                "No supplier cards found — Alibaba may have changed its markup."
            )

        return suppliers

    def _parse_alibaba_card(self, card: Any, product: str) -> dict | None:
        """Parse a single Alibaba offer card into a supplier dict."""
        try:
            # Product title
            title_el = (
                card.select_one(".offer-title") or
                card.select_one("h2") or
                card.select_one("a[title]")
            )
            product_title = (
                title_el.get("title") or title_el.get_text(strip=True)
                if title_el else product.title()
            )

            # Company name
            company_el = (
                card.select_one(".company-name") or
                card.select_one(".supplier-name") or
                card.select_one("[class*='company']")
            )
            supplier_name = company_el.get_text(strip=True) if company_el else "Unknown Supplier"

            # Price range
            price_el = (
                card.select_one(".price") or
                card.select_one("[class*='price']")
            )
            price_range = price_el.get_text(strip=True) if price_el else "Price on request"

            # MOQ
            moq_el = card.select_one("[class*='moq']") or card.select_one("[class*='min-order']")
            min_order_qty = moq_el.get_text(strip=True) if moq_el else "1"

            # Rating / supplier score
            rating_el = card.select_one("[class*='rating']") or card.select_one("[class*='star']")
            rating = rating_el.get_text(strip=True) if rating_el else "N/A"

            # Verification badges
            card_text = card.get_text(" ", strip=True).lower()
            verified_supplier = (
                "verified" in card_text or
                bool(card.select_one("[class*='verified']"))
            )
            trade_assurance = (
                "trade assurance" in card_text or
                bool(card.select_one("[class*='trade-assurance']"))
            )

            # URL
            link_el = card.select_one("a[href]")
            href = link_el["href"] if link_el else ""
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = "https://www.alibaba.com" + href

            return {
                "supplier_name":     supplier_name,
                "product_title":     product_title[:120],
                "price_range":       price_range,
                "min_order_qty":     min_order_qty,
                "rating":            rating,
                "verified_supplier": verified_supplier,
                "trade_assurance":   trade_assurance,
                "url":               href,
                "demo_data":         False,
            }
        except Exception:
            return None

    def _summarise_suppliers(
        self, product: str, suppliers: list[dict], demo_mode: bool
    ) -> str:
        """Build a human-readable supplier summary."""
        verified = sum(1 for s in suppliers if s.get("verified_supplier"))
        ta       = sum(1 for s in suppliers if s.get("trade_assurance"))
        note     = " **(Demo data — live scraping unavailable)**" if demo_mode else ""
        return (
            f"Found {len(suppliers)} Alibaba suppliers for **{product}**{note}. "
            f"{verified} verified supplier(s), {ta} with Trade Assurance. "
            "Review MOQ and price ranges before contacting suppliers."
        )

    # ──────────────────────────────────────────────────────────
    # PROJ-188  PPC Campaign Builder
    # ──────────────────────────────────────────────────────────

    def _run_ppc_builder(self, query: str) -> SkillResult:
        """
        Generate a full Amazon Sponsored Products PPC campaign structure.

        Parses the product/niche from the query and asks Claude to
        produce 20 keywords with match types, suggested bids, daily
        budget recommendation, and ACOS target.
        """
        subject = self._parse_subject(query) or query.strip()

        client = self._get_claude()
        if not client:
            return SkillResult(
                skill_name=self.name,
                query=query,
                success=False,
                error=(
                    "Claude AI is required for PPC campaign generation. "
                    "Set ANTHROPIC_API_KEY in your .env file."
                ),
            )

        prompt = self._ppc_prompt(subject)
        try:
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = message.content[0].text.strip()
        except Exception as exc:
            return SkillResult(
                skill_name=self.name,
                query=query,
                success=False,
                error=f"Claude API error: {exc}",
            )

        campaign_data = self._parse_ppc_response(raw_text, subject)
        keywords      = campaign_data.get("keywords", [])

        summary = (
            f"## PPC Campaign: {campaign_data.get('campaign_name', subject)}\n\n"
            f"**Daily Budget:** {campaign_data.get('daily_budget', 'N/A')}\n"
            f"**Campaign Type:** {campaign_data.get('campaign_type', 'Sponsored Products')}\n"
            f"**ACOS Target:** {campaign_data.get('acos_target', 'N/A')}\n\n"
            f"Generated {len(keywords)} keywords across Broad / Phrase / Exact match types."
        )

        return SkillResult(
            skill_name=self.name,
            query=query,
            success=True,
            results=keywords,
            summary=summary,
            metadata={
                "mode":          "ppc_builder",
                "product":       subject,
                "campaign_name": campaign_data.get("campaign_name", ""),
                "daily_budget":  campaign_data.get("daily_budget", ""),
                "acos_target":   campaign_data.get("acos_target", ""),
                "campaign_type": campaign_data.get("campaign_type", ""),
                "keyword_count": len(keywords),
            },
        )

    @staticmethod
    def _ppc_prompt(product: str) -> str:
        return f"""You are an Amazon PPC expert. Generate a complete Sponsored Products campaign
structure for the following product or niche: "{product}".

Return your response in this exact JSON format (no markdown fences):
{{
  "campaign_name": "<descriptive campaign name>",
  "campaign_type": "Sponsored Products",
  "daily_budget": "$<amount>",
  "acos_target": "<X>%",
  "keywords": [
    {{
      "keyword": "<keyword text>",
      "match_type": "<Broad|Phrase|Exact>",
      "suggested_bid": "$<amount>",
      "estimated_clicks": <integer per day>
    }}
  ]
}}

Requirements:
- Include exactly 20 keywords: ~7 Broad, ~7 Phrase, ~6 Exact.
- Choose keywords that reflect realistic Amazon shopper intent for this product.
- Suggested bids should be realistic (typically $0.30–$3.50).
- Daily budget recommendation should suit a new seller ($20–$80/day).
- ACOS target should be appropriate for the product category.
- Estimated clicks per day should be plausible (1–50).
"""

    @staticmethod
    def _parse_ppc_response(text: str, product: str) -> dict:
        """Parse Claude's JSON campaign response, with graceful fallback."""
        # Strip any accidental markdown fences
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract a JSON object with regex
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        # Absolute fallback — minimal structure
        return {
            "campaign_name": f"{product.title()} — Auto Campaign",
            "campaign_type": "Sponsored Products",
            "daily_budget":  "$30",
            "acos_target":   "25%",
            "keywords":      [],
        }

    # ──────────────────────────────────────────────────────────
    # PROJ-189  Product Progress Analysis
    # ──────────────────────────────────────────────────────────

    def _run_progress_analysis(self, query: str) -> SkillResult:
        """
        Analyse a product's market position and growth trends using Claude.

        Input can be a product name or ASIN.  Returns structured analysis
        covering BSR trend, review velocity, pricing, Buy Box, saturation,
        and growth potential.
        """
        subject = self._parse_subject(query) or query.strip()

        client = self._get_claude()
        if not client:
            return SkillResult(
                skill_name=self.name,
                query=query,
                success=False,
                error=(
                    "Claude AI is required for product progress analysis. "
                    "Set ANTHROPIC_API_KEY in your .env file."
                ),
            )

        prompt = self._progress_prompt(subject)
        try:
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=900,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = message.content[0].text.strip()
        except Exception as exc:
            return SkillResult(
                skill_name=self.name,
                query=query,
                success=False,
                error=f"Claude API error: {exc}",
            )

        analysis = self._parse_progress_response(raw_text)
        insights  = analysis.get("actionable_insights", [])
        results   = [{"insight": ins} for ins in insights]

        summary = self._build_progress_summary(subject, analysis)

        return SkillResult(
            skill_name=self.name,
            query=query,
            success=True,
            results=results,
            summary=summary,
            metadata={
                "mode":                   "progress_analysis",
                "product":                subject,
                "bsr_trend":              analysis.get("bsr_trend", ""),
                "review_velocity":        analysis.get("review_velocity", ""),
                "pricing_history":        analysis.get("pricing_history", ""),
                "buy_box_analysis":       analysis.get("buy_box_analysis", ""),
                "market_saturation":      analysis.get("market_saturation", 0),
                "growth_potential_score": analysis.get("growth_potential_score", 0),
            },
        )

    @staticmethod
    def _progress_prompt(product: str) -> str:
        return f"""You are an Amazon marketplace analyst with deep expertise in product trends.
Analyse the following product or ASIN: "{product}".

Return your analysis in this exact JSON format (no markdown fences):
{{
  "bsr_trend":              "<Improving|Stable|Declining> — <brief reason>",
  "review_velocity":        "<estimated reviews per month, e.g. ~45/month>",
  "pricing_history":        "<brief pricing trend analysis>",
  "buy_box_analysis":       "<who typically wins Buy Box and why>",
  "market_saturation":      <integer 1-10>,
  "growth_potential_score": <integer 1-10>,
  "actionable_insights": [
    "<insight 1>",
    "<insight 2>",
    "<insight 3>",
    "<insight 4>",
    "<insight 5>"
  ]
}}

Guidelines:
- market_saturation: 1=niche/low competition, 10=extremely saturated.
- growth_potential_score: 1=stagnant, 10=explosive growth opportunity.
- actionable_insights must be specific, seller-focused advice.
- Base your estimates on realistic Amazon market dynamics.
"""

    @staticmethod
    def _parse_progress_response(text: str) -> dict:
        """Parse Claude's JSON progress analysis, with graceful fallback."""
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return {
            "bsr_trend":              "Stable — insufficient data",
            "review_velocity":        "N/A",
            "pricing_history":        "N/A",
            "buy_box_analysis":       "N/A",
            "market_saturation":      5,
            "growth_potential_score": 5,
            "actionable_insights":    [text],
        }

    @staticmethod
    def _build_progress_summary(product: str, analysis: dict) -> str:
        saturation = analysis.get("market_saturation", "N/A")
        growth     = analysis.get("growth_potential_score", "N/A")
        insights   = analysis.get("actionable_insights", [])
        lines = [
            f"## Product Progress Analysis: {product}\n",
            f"**BSR Trend:** {analysis.get('bsr_trend', 'N/A')}",
            f"**Review Velocity:** {analysis.get('review_velocity', 'N/A')}",
            f"**Pricing History:** {analysis.get('pricing_history', 'N/A')}",
            f"**Buy Box:** {analysis.get('buy_box_analysis', 'N/A')}",
            f"**Market Saturation:** {saturation}/10",
            f"**Growth Potential:** {growth}/10\n",
            "### Actionable Insights",
        ]
        for i, ins in enumerate(insights, 1):
            lines.append(f"{i}. {ins}")
        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────
    # PROJ-190  Profit Optimiser
    # ──────────────────────────────────────────────────────────

    def _run_profit_optimiser(self, query: str) -> SkillResult:
        """
        Parse selling/cost/fee figures from the query, compute margin
        metrics, then use Claude to generate 5–7 profit-improvement recs.

        Accepted query format examples::

            "optimize profit: selling_price=24.99 cost_price=7.00"
            "optimize profit: price=29.99 cost=8.50 fees=15 ads=12"
        """
        params   = self._parse_profit_params(query)
        selling  = params["selling_price"]
        cost     = params["cost_price"]
        fees_pct = params["amazon_fees_pct"]
        ads_pct  = params["ad_spend_pct"]

        # ── Compute metrics ───────────────────────────────────
        amazon_fees  = round(selling * fees_pct / 100, 2)
        ad_spend     = round(selling * ads_pct / 100, 2)
        gross_profit = round(selling - cost - amazon_fees, 2)
        net_profit   = round(gross_profit - ad_spend, 2)
        gross_margin = round((gross_profit / selling) * 100, 1) if selling else 0.0
        net_margin   = round((net_profit   / selling) * 100, 1) if selling else 0.0
        roi          = round((net_profit   / cost    ) * 100, 1) if cost    else 0.0

        current_metrics = {
            "selling_price":  selling,
            "cost_price":     cost,
            "amazon_fees":    amazon_fees,
            "amazon_fees_pct": fees_pct,
            "ad_spend":       ad_spend,
            "ad_spend_pct":   ads_pct,
            "gross_profit":   gross_profit,
            "net_profit":     net_profit,
            "gross_margin":   f"{gross_margin}%",
            "net_margin":     f"{net_margin}%",
            "roi":            f"{roi}%",
        }

        # ── Ask Claude for recommendations ────────────────────
        client = self._get_claude()
        recommendations: list[str] = []
        recommended_price_range    = ""
        projected_improvement_pct  = 0.0

        if client:
            prompt = self._profit_prompt(current_metrics, query)
            try:
                message = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=800,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw_text = message.content[0].text.strip()
                parsed   = self._parse_profit_response(raw_text)
                recommendations           = parsed.get("recommendations", [])
                recommended_price_range   = parsed.get("recommended_price_range", "")
                projected_improvement_pct = parsed.get("projected_improvement_pct", 0.0)
            except Exception as exc:
                recommendations = [f"Claude AI error: {exc}"]
        else:
            recommendations = [
                "Set ANTHROPIC_API_KEY in .env to get AI-powered profit recommendations."
            ]

        results = [{"recommendation": r} for r in recommendations]
        summary = self._build_profit_summary(
            current_metrics, recommended_price_range,
            projected_improvement_pct, recommendations,
        )

        return SkillResult(
            skill_name=self.name,
            query=query,
            success=True,
            results=results,
            summary=summary,
            metadata={
                "mode":                      "profit_optimiser",
                "current_metrics":           current_metrics,
                "recommended_price_range":   recommended_price_range,
                "projected_improvement_pct": projected_improvement_pct,
                "top_recommendations":       recommendations,
            },
        )

    @staticmethod
    def _parse_profit_params(query: str) -> dict:
        """
        Extract selling_price, cost_price, amazon_fees_pct, ad_spend_pct
        from the query string.  Returns defaults for any missing values.
        """
        defaults = {
            "selling_price":  0.0,
            "cost_price":     0.0,
            "amazon_fees_pct": 15.0,
            "ad_spend_pct":    10.0,
        }

        # Aliases accepted in the query
        field_aliases = {
            "selling_price":   r"selling_price|selling|price|sell",
            "cost_price":      r"cost_price|cost_price|cost",
            "amazon_fees_pct": r"amazon_fees_pct|fees_pct|fees|fee",
            "ad_spend_pct":    r"ad_spend_pct|ads_pct|ads|ad|advertising",
        }

        for field, pattern in field_aliases.items():
            match = re.search(
                rf"(?:{pattern})\s*[=:]\s*([\d.]+)",
                query,
                re.IGNORECASE,
            )
            if match:
                try:
                    defaults[field] = float(match.group(1))
                except ValueError:
                    pass

        return defaults

    @staticmethod
    def _profit_prompt(metrics: dict, original_query: str) -> str:
        return f"""You are an Amazon FBA profitability consultant.
A seller has provided these current metrics:

  Selling price:    ${metrics['selling_price']:.2f}
  Cost price:       ${metrics['cost_price']:.2f}
  Amazon fees:      ${metrics['amazon_fees']:.2f} ({metrics['amazon_fees_pct']}%)
  Ad spend:         ${metrics['ad_spend']:.2f} ({metrics['ad_spend_pct']}%)
  Gross profit:     ${metrics['gross_profit']:.2f}
  Net profit:       ${metrics['net_profit']:.2f}
  Gross margin:     {metrics['gross_margin']}
  Net margin:       {metrics['net_margin']}
  ROI:              {metrics['roi']}

Original query: "{original_query}"

Return your analysis in this exact JSON format (no markdown fences):
{{
  "recommended_price_range": "$<low> – $<high>",
  "projected_improvement_pct": <float, e.g. 18.5>,
  "recommendations": [
    "<specific actionable recommendation 1>",
    "<specific actionable recommendation 2>",
    "<specific actionable recommendation 3>",
    "<specific actionable recommendation 4>",
    "<specific actionable recommendation 5>",
    "<specific actionable recommendation 6>",
    "<specific actionable recommendation 7>"
  ]
}}

Guidelines:
- projected_improvement_pct: realistic net margin improvement if seller follows all recs.
- recommendations: 5–7 items, specific and actionable (not generic advice).
- Consider: pricing strategy, cost reduction, fee optimisation, ad efficiency, bundling.
"""

    @staticmethod
    def _parse_profit_response(text: str) -> dict:
        """Parse Claude's JSON profit recommendations, with graceful fallback."""
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        # Extract bullet points as fallback
        recs = re.findall(r"^\s*[-*•]\s+(.+)$", text, re.MULTILINE)
        return {
            "recommended_price_range":   "",
            "projected_improvement_pct": 0.0,
            "recommendations":           recs or [text],
        }

    @staticmethod
    def _build_profit_summary(
        metrics: dict,
        price_range: str,
        improvement_pct: float,
        recommendations: list[str],
    ) -> str:
        lines = [
            "## Profit Optimisation Report\n",
            "### Current Metrics",
            f"- Selling price: **${metrics['selling_price']:.2f}**",
            f"- Cost price: **${metrics['cost_price']:.2f}**",
            f"- Amazon fees: **${metrics['amazon_fees']:.2f}** ({metrics['amazon_fees_pct']}%)",
            f"- Ad spend: **${metrics['ad_spend']:.2f}** ({metrics['ad_spend_pct']}%)",
            f"- Net profit / unit: **${metrics['net_profit']:.2f}**",
            f"- Net margin: **{metrics['net_margin']}**",
            f"- ROI: **{metrics['roi']}**\n",
        ]
        if price_range:
            lines.append(f"### Recommended Price Range\n{price_range}\n")
        if improvement_pct:
            lines.append(
                f"### Projected Improvement\n"
                f"Implementing these recommendations could improve net margin "
                f"by **~{improvement_pct:.1f}%**.\n"
            )
        if recommendations:
            lines.append("### Top Recommendations")
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"{i}. {rec}")
        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────
    # Shared helpers
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_subject(query: str) -> str:
        """
        Extract the product name from a supplier/seller query.

        Handles both colon-delimited and plain-English forms::

            "find alibaba suppliers for: wireless earbuds" → "wireless earbuds"
            "find suppliers for yoga mats"                 → "yoga mats"
            "alibaba suppliers wireless earbuds"           → "wireless earbuds"
        """
        import re
        if ":" in query:
            return query.split(":", 1)[1].strip()
        # Strip common plain-English prefixes
        cleaned = re.sub(
            r"(?i)^(find\s+)?(alibaba\s+)?(suppliers?|manufacturers?|wholesale)\s+"
            r"(for\s+|of\s+)?",
            "",
            query.strip(),
        ).strip()
        return cleaned if cleaned else ""
