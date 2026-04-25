# skills/amazon.py
# ──────────────────────────────────────────────────────────────
# Amazon Product Research Skill
# Uses scraping (Playwright + BeautifulSoup)
#
# Fix (PROJ-81): Auto-installs Playwright Chromium if missing,
#   reuses browser context across queries, adds human-like delay
#   between requests to avoid Amazon bot detection.
#
# Sprint 1 Enhancements:
#   PROJ-84: BSR + category scraping via product detail page
#   PROJ-85: Updated formatter to display BSR + category
#   PROJ-86: Review page scraper (top 20 reviews)
#   PROJ-87: Claude AI review sentiment analyser
#   PROJ-88: Review sentiment integrated into agent router
#   PROJ-89: Claude AI opportunity scorer (1–10 scale)
#   PROJ-90: Multi-product query loop (3–5 products)
#   PROJ-91: Competitor comparison table formatter (Rich + Markdown)
# ──────────────────────────────────────────────────────────────

import re
import time
import random
import subprocess
import sys
import requests
from urllib.parse import quote_plus

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

try:
    from rich.table import Table
    from rich.console import Console
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from skills.base_skill import BaseSkill, SkillResult
from config.settings import (
    AMAZON_BASE_URL, AMAZON_HEADERS, MAX_RESULTS, REQUEST_TIMEOUT,
    ANTHROPIC_API_KEY, CLAUDE_MODEL,
)


# ── Query mode constants ───────────────────────────────────────
REVIEW_TRIGGERS = {
    "review", "reviews", "sentiment", "analyse reviews", "analyze reviews",
    "what do customers say", "customer feedback", "pros and cons",
    "is it worth", "should i buy",
}
COMPARE_TRIGGERS = {
    "compare", "vs", "versus", "comparison", "which is better",
    "side by side", "differences between",
}
OPPORTUNITY_TRIGGERS = {
    "opportunity", "score", "worth selling", "market gap",
    "profitable", "competition level",
}


def _ensure_playwright_chromium():
    """Auto-install Playwright Chromium browser if not already installed."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception:
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                check=True,
            )
        except Exception:
            pass  # Will fall back to requests if Playwright still fails


# Run once at import time so all queries benefit
_ensure_playwright_chromium()


class AmazonSkill(BaseSkill):
    name        = "amazon"
    description = (
        "Search Amazon for products, compare prices, read ratings and reviews. "
        "Use when the user asks about buying something, product recommendations, "
        "price comparisons, best products, reviews, or anything on Amazon. "
        "Also handles multi-product comparison, review sentiment analysis, "
        "BSR (Best Seller Rank) research, and seller opportunity scoring."
    )
    triggers = [
        "buy", "product", "amazon", "price", "cheap", "best", "review",
        "rating", "recommend", "purchase", "shop", "deal", "sale",
        "under $", "budget", "affordable", "top rated", "bestseller",
        "compare", "vs", "versus", "sentiment", "opportunity", "bsr",
        "best seller rank", "seller", "market", "profitable",
    ]

    # Class-level browser reused across all queries in one session
    _browser      = None
    _pw_context   = None
    _claude_client = None

    # ── Claude client ─────────────────────────────────────────
    @classmethod
    def _get_claude(cls):
        """Lazy-load Claude client once."""
        if not ANTHROPIC_AVAILABLE:
            return None
        if cls._claude_client is None:
            try:
                cls._claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            except Exception:
                pass
        return cls._claude_client

    # ── Browser management ────────────────────────────────────
    @classmethod
    def _get_browser(cls):
        """Launch browser once and reuse. Reconnect if browser was closed."""
        try:
            from playwright.sync_api import sync_playwright
            if cls._pw_context is None:
                cls._pw_context = sync_playwright().start()
            if cls._browser is None or not cls._browser.is_connected():
                cls._browser = cls._pw_context.chromium.launch(headless=True)
            return cls._browser
        except Exception:
            return None

    # ── Main entry point ──────────────────────────────────────
    def run(self, query: str) -> SkillResult:
        if not BS4_AVAILABLE:
            return SkillResult(
                skill_name=self.name,
                query=query,
                success=False,
                error="beautifulsoup4 not installed. Run: pip install beautifulsoup4",
            )

        q_lower = query.lower()

        # ── Mode: Compare multiple products (PROJ-90/91) ──────
        if any(t in q_lower for t in COMPARE_TRIGGERS):
            return self._run_comparison(query)

        # ── Mode: Review sentiment analysis (PROJ-86/87/88) ───
        if any(t in q_lower for t in REVIEW_TRIGGERS):
            return self._run_review_analysis(query)

        # ── Mode: Opportunity scoring (PROJ-89) ───────────────
        if any(t in q_lower for t in OPPORTUNITY_TRIGGERS):
            return self._run_opportunity_score(query)

        # ── Mode: Normal product search ───────────────────────
        return self._run_normal_search(query)

    # ── Normal search ─────────────────────────────────────────
    def _run_normal_search(self, query: str) -> SkillResult:
        try:
            products = self._scrape_amazon(query)
        except Exception as e:
            return SkillResult(
                skill_name=self.name, query=query, success=False, error=str(e),
            )

        products = products[:MAX_RESULTS]

        # Enrich top product with BSR + category (PROJ-84)
        if products and products[0].get("link"):
            try:
                self._enrich_with_detail(products[0])
            except Exception:
                pass  # BSR enrichment is best-effort

        return SkillResult(
            skill_name = self.name,
            query      = query,
            success    = len(products) > 0,
            results    = products,
            summary    = self._build_summary(query, products),
            metadata   = {
                "source":      "Amazon.com (scraped)",
                "total_found": len(products),
                "search_url":  self._build_search_url(query),
                "mode":        "search",
            },
        )

    # ── Comparison mode (PROJ-90 / PROJ-91) ───────────────────
    def _run_comparison(self, query: str) -> SkillResult:
        product_names = self._parse_multi_product_query(query)

        if len(product_names) < 2:
            # Could not parse multiple products, fall back to normal search
            return self._run_normal_search(query)

        all_products = []
        for name in product_names[:5]:  # cap at 5 products
            try:
                time.sleep(random.uniform(1.0, 2.0))  # polite delay between searches
                results = self._scrape_amazon(name)
                if results:
                    top = results[0]
                    top["search_query"] = name
                    try:
                        self._enrich_with_detail(top)
                    except Exception:
                        pass
                    all_products.append(top)
            except Exception:
                pass

        if not all_products:
            return SkillResult(
                skill_name=self.name, query=query, success=False,
                error="Could not retrieve products for comparison.",
            )

        # Score each product (PROJ-89)
        for p in all_products:
            try:
                score_data = self._score_opportunity(p, None)
                p["opportunity_score"]  = score_data.get("score", "N/A")
                p["opportunity_reason"] = score_data.get("reason", "")
            except Exception:
                p["opportunity_score"]  = "N/A"
                p["opportunity_reason"] = ""

        comparison_table = self._format_comparison_table(all_products)

        return SkillResult(
            skill_name = self.name,
            query      = query,
            success    = True,
            results    = all_products,
            summary    = comparison_table,
            metadata   = {
                "source":        "Amazon.com (scraped)",
                "total_found":   len(all_products),
                "products_compared": [p.get("search_query", p.get("title","?")[:40]) for p in all_products],
                "mode":          "comparison",
            },
        )

    # ── Review sentiment mode (PROJ-86 / PROJ-87 / PROJ-88) ───
    def _run_review_analysis(self, query: str) -> SkillResult:
        # Strip review trigger words to isolate the product name
        product_query = query
        for t in ["analyze reviews for", "analyse reviews for", "reviews for",
                  "reviews of", "sentiment for", "what do customers say about",
                  "should i buy", "is it worth buying", "pros and cons of"]:
            product_query = re.sub(re.escape(t), "", product_query, flags=re.IGNORECASE).strip()

        if not product_query or len(product_query) < 3:
            product_query = query  # fallback

        try:
            products = self._scrape_amazon(product_query)
        except Exception as e:
            return SkillResult(
                skill_name=self.name, query=query, success=False, error=str(e),
            )

        if not products:
            return SkillResult(
                skill_name=self.name, query=query, success=False,
                error=f"No products found for '{product_query}'.",
            )

        product = products[0]
        try:
            self._enrich_with_detail(product)
        except Exception:
            pass

        # Scrape reviews (PROJ-86)
        reviews = []
        review_error = ""
        if product.get("asin"):
            try:
                reviews = self._scrape_reviews(product["asin"])
            except Exception as e:
                review_error = str(e)

        # Analyse sentiment with Claude (PROJ-87)
        sentiment = {}
        if reviews:
            try:
                sentiment = self._analyse_sentiment(reviews, product.get("title", product_query))
            except Exception:
                pass

        summary = self._build_review_summary(product, reviews, sentiment)

        return SkillResult(
            skill_name = self.name,
            query      = query,
            success    = True,
            results    = reviews,
            summary    = summary,
            error      = review_error,
            metadata   = {
                "product":          product,
                "sentiment":        sentiment,
                "reviews_scraped":  len(reviews),
                "mode":             "review_analysis",
            },
        )

    # ── Opportunity score mode (PROJ-89) ──────────────────────
    def _run_opportunity_score(self, query: str) -> SkillResult:
        # Strip opportunity trigger words
        product_query = query
        for t in ["opportunity score for", "opportunity for", "score for",
                  "is it worth selling", "worth selling"]:
            product_query = re.sub(re.escape(t), "", product_query, flags=re.IGNORECASE).strip()

        if not product_query or len(product_query) < 3:
            product_query = query

        try:
            products = self._scrape_amazon(product_query)
        except Exception as e:
            return SkillResult(
                skill_name=self.name, query=query, success=False, error=str(e),
            )

        if not products:
            return SkillResult(
                skill_name=self.name, query=query, success=False,
                error=f"No products found for '{product_query}'.",
            )

        top = products[:5]
        for p in top:
            try:
                self._enrich_with_detail(p)
            except Exception:
                pass

        scores = []
        for p in top:
            try:
                score_data = self._score_opportunity(p, None)
                p["opportunity_score"]  = score_data.get("score", "N/A")
                p["opportunity_reason"] = score_data.get("reason", "")
                scores.append(p)
            except Exception:
                p["opportunity_score"] = "N/A"
                scores.append(p)

        summary = self._build_opportunity_summary(product_query, scores)

        return SkillResult(
            skill_name = self.name,
            query      = query,
            success    = True,
            results    = scores,
            summary    = summary,
            metadata   = {
                "source": "Amazon.com (scraped)",
                "mode":   "opportunity_score",
            },
        )

    # ── BSR + category detail scraper (PROJ-84) ───────────────
    def _scrape_product_detail(self, url: str) -> dict:
        """Visit a product page and extract BSR, category, and full description."""
        detail = {"bsr": "", "category": "", "description": ""}
        if not url or not url.startswith("http"):
            return detail

        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import stealth_sync

            browser = self._get_browser()
            if browser is None:
                raise Exception("Playwright unavailable")

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            stealth_sync(page)
            time.sleep(random.uniform(1.0, 2.0))
            page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
            time.sleep(random.uniform(0.5, 1.0))
            html = page.content()
            context.close()

            soup = BeautifulSoup(html, "html.parser")

            # BSR is in the product details table
            bsr_pattern = re.compile(r"best\s+seller", re.IGNORECASE)
            for row in soup.find_all("tr"):
                row_text = row.get_text(" ", strip=True)
                if bsr_pattern.search(row_text):
                    cells = row.find_all(["th", "td"])
                    if len(cells) >= 2:
                        bsr_text = cells[-1].get_text(" ", strip=True)
                        match = re.search(r"#([\d,]+)\s+in\s+(.+?)(?:\s*\(|$)", bsr_text)
                        if match:
                            detail["bsr"]      = f"#{match.group(1)}"
                            detail["category"] = match.group(2).strip()
                        break

            # Also check the bullet-point detail section
            if not detail["bsr"]:
                for li in soup.select("#detailBullets_feature_div li, #productDetails_techSpec_section_1 tr"):
                    li_text = li.get_text(" ", strip=True)
                    if bsr_pattern.search(li_text):
                        match = re.search(r"#([\d,]+)\s+in\s+(.+?)(?:\s*\(|$)", li_text)
                        if match:
                            detail["bsr"]      = f"#{match.group(1)}"
                            detail["category"] = match.group(2).strip()
                        break

            # Product description
            desc_el = (
                soup.select_one("#productDescription") or
                soup.select_one("#feature-bullets")
            )
            if desc_el:
                detail["description"] = desc_el.get_text(" ", strip=True)[:500]

        except Exception:
            pass  # Best-effort; caller handles empty dict

        return detail

    def _enrich_with_detail(self, product: dict) -> None:
        """Enrich a product dict in-place with BSR + category. (PROJ-84)"""
        if not product.get("link"):
            return
        detail = self._scrape_product_detail(product["link"])
        product["bsr"]         = detail.get("bsr", "")
        product["category"]    = detail.get("category", "")
        product["description"] = detail.get("description", "")

    # ── Review scraper (PROJ-86) ──────────────────────────────
    def _scrape_reviews(self, asin: str) -> list[dict]:
        """Scrape top 20 customer reviews from the Amazon review page."""
        reviews_url = f"{AMAZON_BASE_URL}/product-reviews/{asin}/?sortBy=recent&pageSize=20"
        html = ""

        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import stealth_sync

            browser = self._get_browser()
            if browser is None:
                raise Exception("Playwright unavailable")

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            stealth_sync(page)
            time.sleep(random.uniform(1.5, 3.0))
            page.goto(reviews_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            time.sleep(random.uniform(0.8, 1.5))
            html = page.content()
            context.close()

        except Exception:
            try:
                resp = requests.get(reviews_url, headers=AMAZON_HEADERS, timeout=REQUEST_TIMEOUT)
                html = resp.text
            except Exception:
                return []

        if not html:
            return []

        soup    = BeautifulSoup(html, "html.parser")
        reviews = []

        for review_div in soup.select("[data-hook='review']")[:20]:
            try:
                # Star rating
                star_el    = review_div.select_one("[data-hook='review-star-rating'] .a-icon-alt")
                star_text  = star_el.get_text(strip=True) if star_el else ""
                star_match = re.search(r"[\d.]+", star_text)
                stars      = float(star_match.group()) if star_match else 0.0

                # Review title
                title_el = review_div.select_one("[data-hook='review-title'] span:not(.a-icon-alt)")
                title    = title_el.get_text(strip=True) if title_el else ""

                # Review body
                body_el = review_div.select_one("[data-hook='review-body'] span")
                body    = body_el.get_text(strip=True) if body_el else ""

                # Review date
                date_el = review_div.select_one("[data-hook='review-date']")
                date    = date_el.get_text(strip=True) if date_el else ""

                # Verified purchase
                verified_el = review_div.select_one("[data-hook='avp-badge']")
                verified    = verified_el is not None

                if title or body:
                    reviews.append({
                        "stars":    stars,
                        "title":    title,
                        "body":     body[:600],
                        "date":     date,
                        "verified": verified,
                    })
            except Exception:
                continue

        return reviews

    # ── Sentiment analyser (PROJ-87) ──────────────────────────
    def _analyse_sentiment(self, reviews: list[dict], product_title: str) -> dict:
        """Use Claude to analyse review sentiment and extract themes."""
        client = self._get_claude()
        if not client or not reviews:
            return {}

        # Build review text for Claude
        review_text = "\n\n".join(
            f"[{r['stars']} stars] {r['title']}: {r['body']}"
            for r in reviews[:20]
        )

        prompt = f"""Analyse the following Amazon customer reviews for: "{product_title}"

Reviews:
{review_text}

Provide a structured analysis with:
1. Overall sentiment (Positive/Mixed/Negative) with percentage breakdown (e.g. 70% positive, 20% mixed, 10% negative)
2. Top 3 PROS customers mention
3. Top 3 CONS customers mention
4. Most common use case mentioned
5. One-sentence verdict for a potential buyer

Format your response exactly like this:
OVERALL: <Positive/Mixed/Negative> (<X>% positive, <Y>% mixed, <Z>% negative)
PROS:
- <pro 1>
- <pro 2>
- <pro 3>
CONS:
- <con 1>
- <con 2>
- <con 3>
USE_CASE: <most common use case>
VERDICT: <one-sentence buyer verdict>"""

        try:
            message = client.messages.create(
                model      = CLAUDE_MODEL,
                max_tokens = 400,
                messages   = [{"role": "user", "content": prompt}],
            )
            response = message.content[0].text.strip()
            return self._parse_sentiment_response(response)
        except Exception:
            return {}

    def _parse_sentiment_response(self, text: str) -> dict:
        """Parse Claude's structured sentiment response into a dict."""
        result = {
            "overall": "", "positive_pct": 0, "mixed_pct": 0, "negative_pct": 0,
            "pros": [], "cons": [], "use_case": "", "verdict": "", "raw": text,
        }

        # Overall line
        overall_match = re.search(r"OVERALL:\s*(.+)", text)
        if overall_match:
            overall_line = overall_match.group(1)
            result["overall"] = overall_line.split("(")[0].strip()
            pct_matches = re.findall(r"(\d+)%\s*(positive|mixed|negative)", overall_line, re.I)
            for val, label in pct_matches:
                result[f"{label.lower()}_pct"] = int(val)

        # Pros
        pros_match = re.search(r"PROS:\n((?:- .+\n?)+)", text)
        if pros_match:
            result["pros"] = [
                line.lstrip("- ").strip()
                for line in pros_match.group(1).strip().split("\n")
                if line.strip().startswith("-")
            ]

        # Cons
        cons_match = re.search(r"CONS:\n((?:- .+\n?)+)", text)
        if cons_match:
            result["cons"] = [
                line.lstrip("- ").strip()
                for line in cons_match.group(1).strip().split("\n")
                if line.strip().startswith("-")
            ]

        # Use case
        use_match = re.search(r"USE_CASE:\s*(.+)", text)
        if use_match:
            result["use_case"] = use_match.group(1).strip()

        # Verdict
        verdict_match = re.search(r"VERDICT:\s*(.+)", text)
        if verdict_match:
            result["verdict"] = verdict_match.group(1).strip()

        return result

    # ── Opportunity scorer (PROJ-89) ──────────────────────────
    def _score_opportunity(self, product: dict, sentiment: dict | None) -> dict:
        """Use Claude to score a product's seller opportunity on a 1–10 scale."""
        client = self._get_claude()
        if not client:
            return {"score": "N/A", "reason": "Claude AI not available"}

        title     = product.get("title", "Unknown product")[:120]
        price     = product.get("price", "N/A")
        rating    = product.get("rating", "N/A")
        reviews   = product.get("reviews", "N/A")
        prime     = product.get("prime", False)
        bsr       = product.get("bsr", "N/A")
        category  = product.get("category", "N/A")

        sentiment_str = ""
        if sentiment:
            sentiment_str = (
                f"\nReview sentiment: {sentiment.get('overall','N/A')} "
                f"({sentiment.get('positive_pct',0)}% positive)"
                f"\nTop cons: {', '.join(sentiment.get('cons', []))}"
            )

        prompt = f"""You are an Amazon seller intelligence analyst. Evaluate this product as a selling opportunity.

Product: {title}
Price: {price}
Rating: {rating}
Review count: {reviews}
Prime eligible: {prime}
Best Seller Rank: {bsr}
Category: {category}{sentiment_str}

Score this product as a SELLER opportunity from 1 to 10, where:
- 10 = Exceptional opportunity (high demand, low competition, good margins)
- 7-9 = Good opportunity (strong demand indicators)
- 4-6 = Moderate (competitive market, proceed with caution)
- 1-3 = Poor (saturated, low margins, or too competitive)

Respond in exactly this format:
SCORE: <number 1-10>
REASON: <2-3 sentence explanation covering demand signals, competition level, and key risk/opportunity>"""

        try:
            message = client.messages.create(
                model      = CLAUDE_MODEL,
                max_tokens = 200,
                messages   = [{"role": "user", "content": prompt}],
            )
            response = message.content[0].text.strip()

            score_match  = re.search(r"SCORE:\s*(\d+)", response)
            reason_match = re.search(r"REASON:\s*(.+)", response, re.DOTALL)

            return {
                "score":  int(score_match.group(1)) if score_match else "N/A",
                "reason": reason_match.group(1).strip() if reason_match else response,
            }
        except Exception as e:
            return {"score": "N/A", "reason": str(e)}

    # ── Multi-product query parser (PROJ-90) ──────────────────
    def _parse_multi_product_query(self, query: str) -> list[str]:
        """Extract individual product names from a comparison query."""
        q = query.strip()

        # Pattern: "compare X vs Y" or "X vs Y vs Z"
        vs_pattern = re.compile(r"\s+(?:vs\.?|versus)\s+", re.IGNORECASE)
        if vs_pattern.search(q):
            # Remove trigger words like "compare"
            q = re.sub(r"^compare\s+", "", q, flags=re.IGNORECASE).strip()
            parts = vs_pattern.split(q)
            return [p.strip() for p in parts if p.strip()]

        # Pattern: "compare X and Y" or "compare X, Y and Z"
        and_pattern = re.compile(r"\bcompare\b", re.IGNORECASE)
        if and_pattern.search(q):
            q = and_pattern.sub("", q).strip()
            # Split on "and" or commas
            parts = re.split(r",\s*|\s+and\s+", q, flags=re.IGNORECASE)
            clean = [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]
            if len(clean) >= 2:
                return clean

        # Pattern: comma-separated list with "comparison" keyword
        if "comparison" in q.lower():
            q = re.sub(r"\bcomparison\b", "", q, flags=re.IGNORECASE).strip()
            parts = re.split(r",\s*|\s+and\s+", q, flags=re.IGNORECASE)
            clean = [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]
            if len(clean) >= 2:
                return clean

        return []  # Could not parse multiple products

    # ── Comparison table formatter (PROJ-91) ──────────────────
    def _format_comparison_table(self, products: list[dict]) -> str:
        """Format a multi-product comparison as a Rich terminal table + Markdown fallback."""

        # Try Rich first for rich terminal rendering
        if RICH_AVAILABLE:
            table = Table(
                title="Amazon Product Comparison",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan",
                show_lines=True,
            )
            table.add_column("Product",           style="white",      max_width=35, no_wrap=False)
            table.add_column("Price",             style="green",      justify="right")
            table.add_column("Rating",            style="yellow",     justify="center")
            table.add_column("Reviews",           style="cyan",       justify="right")
            table.add_column("BSR",               style="magenta",    justify="right")
            table.add_column("Prime",             style="blue",       justify="center")
            table.add_column("Opportunity (1-10)", style="bold green", justify="center")

            for p in products:
                title = (p.get("title") or p.get("search_query", "?"))[:35]
                table.add_row(
                    title,
                    p.get("price", "N/A"),
                    p.get("rating", "N/A"),
                    p.get("reviews", "N/A"),
                    p.get("bsr", "N/A"),
                    "YES" if p.get("prime") else "NO",
                    str(p.get("opportunity_score", "N/A")),
                )

            from io import StringIO
            console = Console(file=StringIO(), width=120)
            console.print(table)
            rich_output = console.file.getvalue()
        else:
            rich_output = ""

        # Always generate a Markdown table as universal fallback
        md_lines = [
            "## Amazon Product Comparison\n",
            "| Product | Price | Rating | Reviews | BSR | Prime | Opportunity Score |",
            "|---------|-------|--------|---------|-----|-------|-------------------|",
        ]
        for p in products:
            title = (p.get("title") or p.get("search_query", "?"))[:40]
            title = title.replace("|", "")
            md_lines.append(
                f"| {title} | {p.get('price','N/A')} | {p.get('rating','N/A')} "
                f"| {p.get('reviews','N/A')} | {p.get('bsr','N/A')} "
                f"| {'YES' if p.get('prime') else 'NO'} "
                f"| {p.get('opportunity_score','N/A')} |"
            )

        # Add opportunity reasons below the table
        md_lines.append("\n### Opportunity Analysis")
        for p in products:
            title = (p.get("title") or p.get("search_query", "?"))[:60]
            score  = p.get("opportunity_score", "N/A")
            reason = p.get("opportunity_reason", "")
            if reason:
                md_lines.append(f"\n**{title}** — Score: {score}/10\n{reason}")

        md_output = "\n".join(md_lines)

        # Return Rich output if available, Markdown otherwise
        return (rich_output + "\n\n" + md_output).strip() if rich_output else md_output

    # ── Summary builders (PROJ-85) ────────────────────────────
    def _build_summary(self, query: str, products: list[dict]) -> str:
        """Build a text summary including BSR/category when available."""
        if not products:
            return (
                f"No Amazon products found for '{query}'. "
                "Amazon may have blocked the request — try again or use a VPN/proxy."
            )

        prices = []
        for p in products:
            raw = re.sub(r"[^\d.]", "", p.get("price", ""))
            try:
                prices.append(float(raw))
            except ValueError:
                pass

        price_info  = f" Price range: ${min(prices):.2f} – ${max(prices):.2f}." if prices else ""
        prime_count = sum(1 for p in products if p.get("prime"))
        prime_info  = f" {prime_count} Prime-eligible." if prime_count else ""

        # BSR info for top product (PROJ-85 enhancement)
        bsr_info = ""
        if products[0].get("bsr"):
            bsr_info = (
                f" Top result BSR: {products[0]['bsr']}"
                + (f" in {products[0]['category']}" if products[0].get("category") else "")
                + "."
            )

        return (
            f"Found {len(products)} Amazon products for '{query}'."
            f"{price_info}{prime_info}{bsr_info}"
        )

    def _build_review_summary(self, product: dict, reviews: list[dict], sentiment: dict) -> str:
        """Build a review analysis summary."""
        title = product.get("title", "this product")[:80]
        lines = [f"## Review Analysis: {title}\n"]

        if not reviews:
            lines.append("Could not retrieve reviews. Try again or check the product URL.")
            return "\n".join(lines)

        lines.append(f"Analysed **{len(reviews)} reviews**.\n")

        if sentiment:
            lines.append(f"**Overall Sentiment:** {sentiment.get('overall', 'N/A')}")
            pos = sentiment.get("positive_pct", 0)
            mix = sentiment.get("mixed_pct", 0)
            neg = sentiment.get("negative_pct", 0)
            if pos or mix or neg:
                lines.append(f"({pos}% positive · {mix}% mixed · {neg}% negative)\n")

            if sentiment.get("pros"):
                lines.append("**Pros:**")
                for pro in sentiment["pros"]:
                    lines.append(f"- {pro}")

            if sentiment.get("cons"):
                lines.append("\n**Cons:**")
                for con in sentiment["cons"]:
                    lines.append(f"- {con}")

            if sentiment.get("use_case"):
                lines.append(f"\n**Most common use case:** {sentiment['use_case']}")

            if sentiment.get("verdict"):
                lines.append(f"\n**Verdict:** {sentiment['verdict']}")
        else:
            # Basic stats without Claude
            avg_stars = sum(r.get("stars", 0) for r in reviews) / len(reviews) if reviews else 0
            lines.append(f"Average rating from scraped reviews: {avg_stars:.1f} / 5.0")

        return "\n".join(lines)

    def _build_opportunity_summary(self, query: str, products: list[dict]) -> str:
        """Build opportunity score summary."""
        lines = [f"## Seller Opportunity Analysis: {query}\n"]
        for p in products:
            title = (p.get("title") or "?")[:80]
            score  = p.get("opportunity_score", "N/A")
            reason = p.get("opportunity_reason", "")
            bsr    = p.get("bsr", "")
            bsr_str = f" | BSR: {bsr}" if bsr else ""
            lines.append(
                f"**{title}**\n"
                f"Price: {p.get('price','N/A')} | Rating: {p.get('rating','N/A')} "
                f"| Reviews: {p.get('reviews','N/A')}{bsr_str}\n"
                f"Opportunity Score: **{score}/10**\n"
                f"{reason}\n"
            )
        return "\n".join(lines)

    # ── Core scraper (unchanged) ───────────────────────────────
    def _scrape_amazon(self, query: str) -> list[dict]:
        url  = self._build_search_url(query)
        html = ""

        # Human-like delay: 1.5–3s between queries to avoid bot detection
        time.sleep(random.uniform(1.5, 3.0))

        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import stealth_sync

            browser = self._get_browser()
            if browser is None:
                raise Exception("Playwright browser unavailable")

            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            stealth_sync(page)
            page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            time.sleep(random.uniform(0.8, 1.5))
            html = page.content()
            context.close()   # Close context (not browser) — browser stays warm

        except Exception:
            # Fallback to requests if Playwright fails
            resp = requests.get(url, headers=AMAZON_HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            html = resp.text

        soup     = BeautifulSoup(html, "html.parser")
        products = []

        cards = soup.select('[data-component-type="s-search-result"]')
        for card in cards:
            product = self._parse_card(card)
            if product and product.get("title"):
                products.append(product)

        if not products:
            products = self._fallback_parse(soup)

        return products

    def _parse_card(self, card) -> dict | None:
        """Parse a search result card into a product dict."""
        try:
            title_el = card.select_one("h2 a span") or card.select_one(".a-size-medium")
            title    = title_el.get_text(strip=True) if title_el else ""

            price_whole = card.select_one(".a-price-whole")
            price_frac  = card.select_one(".a-price-fraction")
            if price_whole:
                price = f"${price_whole.get_text(strip=True)}"
                if price_frac:
                    price += price_frac.get_text(strip=True)
            else:
                price_el = card.select_one(".a-price .a-offscreen")
                price    = price_el.get_text(strip=True) if price_el else "Price not listed"

            rating_el = card.select_one(".a-icon-star-small .a-icon-alt") or \
                        card.select_one("[aria-label*='out of 5 stars']")
            rating = ""
            if rating_el:
                rating_text = rating_el.get("aria-label") or rating_el.get_text()
                match = re.search(r"[\d.]+", rating_text)
                rating = f"{match.group()} / 5" if match else rating_text

            reviews_el = card.select_one(".a-size-small .a-link-normal")
            reviews    = reviews_el.get_text(strip=True) if reviews_el else ""

            link_el = card.select_one("h2 a") or card.select_one("a.a-link-normal")
            href    = link_el.get("href", "") if link_el else ""
            link    = f"{AMAZON_BASE_URL}{href}" if href.startswith("/") else href

            prime = bool(card.select_one(".s-prime") or card.select_one("[aria-label='Amazon Prime']"))

            img_el = card.select_one("img.s-image")
            image  = img_el.get("src", "") if img_el else ""

            asin = card.get("data-asin", "")

            return {
                "title":       title,
                "price":       price,
                "rating":      rating,
                "reviews":     reviews,
                "prime":       prime,
                "asin":        asin,
                "link":        link,
                "image":       image,
                "source":      "Amazon",
                "bsr":         "",        # Filled in by _enrich_with_detail (PROJ-84)
                "category":    "",        # Filled in by _enrich_with_detail (PROJ-84)
                "description": "",        # Filled in by _enrich_with_detail
            }
        except Exception:
            return None

    def _fallback_parse(self, soup) -> list[dict]:
        products = []
        for el in soup.select(".s-result-item[data-asin]")[:MAX_RESULTS]:
            asin = el.get("data-asin", "")
            if not asin:
                continue
            title_el = el.select_one(".a-text-normal")
            price_el = el.select_one(".a-price .a-offscreen")
            products.append({
                "title":       title_el.get_text(strip=True) if title_el else f"Product {asin}",
                "price":       price_el.get_text(strip=True) if price_el else "N/A",
                "rating":      "",
                "reviews":     "",
                "prime":       False,
                "asin":        asin,
                "link":        f"{AMAZON_BASE_URL}/dp/{asin}",
                "image":       "",
                "source":      "Amazon",
                "bsr":         "",
                "category":    "",
                "description": "",
            })
        return products

    # ── Helpers ───────────────────────────────────────────────
    def _build_search_url(self, query: str) -> str:
        return f"{AMAZON_BASE_URL}/s?k={quote_plus(query)}"
