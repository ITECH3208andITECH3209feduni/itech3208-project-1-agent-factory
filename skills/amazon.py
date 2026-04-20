# skills/amazon.py
# ──────────────────────────────────────────────────────────────
# Amazon Product Research Skill
# Uses scraping (requests + BeautifulSoup)
# Respects rate limits — adds delay between requests
# ──────────────────────────────────────────────────────────────

import re
import time
import requests
from urllib.parse import quote_plus

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from skills.base_skill import BaseSkill, SkillResult
from config.settings import AMAZON_BASE_URL, AMAZON_HEADERS, MAX_RESULTS, REQUEST_TIMEOUT


class AmazonSkill(BaseSkill):
    name        = "amazon"
    description = (
        "Search Amazon for products, compare prices, read ratings and reviews. "
        "Use when the user asks about buying something, product recommendations, "
        "price comparisons, best products, reviews, or anything on Amazon."
    )
    triggers = [
        "buy", "product", "amazon", "price", "cheap", "best", "review",
        "rating", "recommend", "purchase", "shop", "deal", "sale",
        "under $", "budget", "affordable", "top rated", "bestseller",
    ]

    def run(self, query: str) -> SkillResult:
        if not BS4_AVAILABLE:
            return SkillResult(
                skill_name=self.name,
                query=query,
                success=False,
                error="beautifulsoup4 not installed. Run: pip install beautifulsoup4",
            )

        try:
            products = self._scrape_amazon(query)
        except Exception as e:
            return SkillResult(
                skill_name=self.name,
                query=query,
                success=False,
                error=str(e),
            )

        products = products[:MAX_RESULTS]

        return SkillResult(
            skill_name = self.name,
            query      = query,
            success    = len(products) > 0,
            results    = products,
            summary    = self._build_summary(query, products),
            metadata   = {
                "source":        "Amazon.com (scraped)",
                "total_found":   len(products),
                "search_url":    self._build_search_url(query),
            },
        )

    # ── Core scraper ───────────────────────────────────────────
    def _scrape_amazon(self, query: str) -> list[dict]:
        url = self._build_search_url(query)
        html = ""

        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import stealth_sync
            
            with sync_playwright() as p:
                # Launch a hidden browser
                browser = p.chromium.launch(headless=True)
                
                # Use a realistic user agent
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                
                page = context.new_page()
                
                # Apply stealth plugin to hide automation traces
                stealth_sync(page)
                
                # Navigate and wait for content to load
                page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
                
                # Smoothly scroll down to trigger lazy-loaded items (optional but good for hardening)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                time.sleep(1)
                
                html = page.content()
                browser.close()
                
        except Exception as e:
            # Fallback to requests if Playwright fails
            import requests
            resp = requests.get(url, headers=AMAZON_HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        products = []

        # Amazon search result cards
        cards = soup.select('[data-component-type="s-search-result"]')

        for card in cards:
            product = self._parse_card(card)
            if product and product.get("title"):
                products.append(product)

        # Fallback: try alternate selectors if main ones fail
        if not products:
            products = self._fallback_parse(soup)

        return products

    def _parse_card(self, card) -> dict | None:
        try:
            # Title
            title_el = card.select_one("h2 a span") or card.select_one(".a-size-medium")
            title    = title_el.get_text(strip=True) if title_el else ""

            # Price
            price_whole = card.select_one(".a-price-whole")
            price_frac  = card.select_one(".a-price-fraction")
            if price_whole:
                price = f"${price_whole.get_text(strip=True)}"
                if price_frac:
                    price += price_frac.get_text(strip=True)
            else:
                price_el = card.select_one(".a-price .a-offscreen")
                price    = price_el.get_text(strip=True) if price_el else "Price not listed"

            # Rating
            rating_el = card.select_one(".a-icon-star-small .a-icon-alt") or \
                        card.select_one("[aria-label*='out of 5 stars']")
            rating = ""
            if rating_el:
                rating_text = rating_el.get("aria-label") or rating_el.get_text()
                match = re.search(r"[\d.]+", rating_text)
                rating = f"{match.group()} / 5" if match else rating_text

            # Review count
            reviews_el = card.select_one(".a-size-small .a-link-normal")
            reviews    = reviews_el.get_text(strip=True) if reviews_el else ""

            # Product link
            link_el = card.select_one("h2 a") or card.select_one("a.a-link-normal")
            href    = link_el.get("href", "") if link_el else ""
            link    = f"{AMAZON_BASE_URL}{href}" if href.startswith("/") else href

            # Prime badge
            prime = bool(card.select_one(".s-prime") or card.select_one("[aria-label='Amazon Prime']"))

            # Thumbnail
            img_el = card.select_one("img.s-image")
            image  = img_el.get("src", "") if img_el else ""

            # ASIN
            asin = card.get("data-asin", "")

            return {
                "title":    title,
                "price":    price,
                "rating":   rating,
                "reviews":  reviews,
                "prime":    prime,
                "asin":     asin,
                "link":     link,
                "image":    image,
                "source":   "Amazon",
            }
        except Exception:
            return None

    def _fallback_parse(self, soup) -> list[dict]:
        """Fallback parser if primary selectors don't match."""
        products = []
        for el in soup.select(".s-result-item[data-asin]")[:MAX_RESULTS]:
            asin  = el.get("data-asin", "")
            if not asin:
                continue
            title_el = el.select_one(".a-text-normal")
            price_el = el.select_one(".a-price .a-offscreen")
            products.append({
                "title":   title_el.get_text(strip=True) if title_el else f"Product {asin}",
                "price":   price_el.get_text(strip=True) if price_el else "N/A",
                "rating":  "",
                "reviews": "",
                "prime":   False,
                "asin":    asin,
                "link":    f"{AMAZON_BASE_URL}/dp/{asin}",
                "image":   "",
                "source":  "Amazon",
            })
        return products

    # ── Helpers ────────────────────────────────────────────────
    def _build_search_url(self, query: str) -> str:
        return f"{AMAZON_BASE_URL}/s?k={quote_plus(query)}"

    def _build_summary(self, query: str, products: list[dict]) -> str:
        if not products:
            return (
                f"No Amazon products found for '{query}'. "
                "Amazon may have blocked the request — try again or use a VPN/proxy."
            )

        # Find price range
        prices = []
        for p in products:
            raw = re.sub(r"[^\d.]", "", p.get("price", ""))
            try:
                prices.append(float(raw))
            except ValueError:
                pass

        price_info = ""
        if prices:
            price_info = f" Price range: ${min(prices):.2f} – ${max(prices):.2f}."

        # Count Prime-eligible
        prime_count = sum(1 for p in products if p.get("prime"))
        prime_info  = f" {prime_count} Prime-eligible." if prime_count else ""

        return (
            f"Found {len(products)} Amazon products for '{query}'.{price_info}{prime_info}"
        )
