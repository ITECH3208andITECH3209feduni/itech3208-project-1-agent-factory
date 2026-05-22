# components/seller_cards.py
# ──────────────────────────────────────────────────────────────
# Typed dataclasses for Amazon Seller skill results
# Used by the Web UI to render supplier and keyword cards.
#
# PROJ-187  SupplierCard — Alibaba supplier result
# PROJ-188  CampaignCard — PPC keyword / campaign item
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

from dataclasses import dataclass, field


# ── SupplierCard ───────────────────────────────────────────────

@dataclass
class SupplierCard:
    """
    Typed representation of a single Alibaba supplier result.

    Attributes:
        supplier_name    Human-readable company name.
        product_title    Title of the specific product listing.
        price_range      Display string, e.g. ``"$2.50 - $5.00"``.
        moq              Minimum order quantity as a display string,
                         e.g. ``"100 pieces"``.
        rating           Supplier rating string, e.g. ``"4.8"`` or ``"N/A"``.
        verified         True when the supplier carries Alibaba's
                         Verified Supplier badge.
        trade_assurance  True when Trade Assurance is available for
                         buyer protection.
        url              Direct URL to the product/supplier page.
        demo_data        True when this record was generated as mock
                         fallback data (live scraping unavailable).
    """

    supplier_name:   str  = "Unknown Supplier"
    product_title:   str  = ""
    price_range:     str  = "Price on request"
    moq:             str  = "1"
    rating:          str  = "N/A"
    verified:        bool = False
    trade_assurance: bool = False
    url:             str  = ""
    demo_data:       bool = False

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dictionary of this card's fields."""
        return {
            "supplier_name":   self.supplier_name,
            "product_title":   self.product_title,
            "price_range":     self.price_range,
            "moq":             self.moq,
            "rating":          self.rating,
            "verified":        self.verified,
            "trade_assurance": self.trade_assurance,
            "url":             self.url,
            "demo_data":       self.demo_data,
        }

    def to_html_card(self) -> str:
        """Render a self-contained HTML card for Web UI use."""
        url_attr    = f'href="{self.url}"' if self.url else 'href="#"'
        verified_badge = (
            '<span class="badge badge-verified">Verified</span>'
            if self.verified else ""
        )
        ta_badge = (
            '<span class="badge badge-trade-assurance">Trade Assurance</span>'
            if self.trade_assurance else ""
        )
        demo_banner = (
            '<div class="card-demo-notice">Demo data — live scraping unavailable</div>'
            if self.demo_data else ""
        )
        return (
            f'<div class="card supplier-card">'
            f'{demo_banner}'
            f'<div class="card-body">'
            f'<a {url_attr} target="_blank" class="card-title">{self.supplier_name}</a>'
            f'<div class="card-product-title">{self.product_title}</div>'
            f'<div class="card-meta">'
            f'<span class="card-price-range">{self.price_range}</span>'
            f'<span class="card-moq">MOQ: {self.moq}</span>'
            f'<span class="card-rating">Rating: {self.rating}</span>'
            f'</div>'
            f'<div class="card-badges">{verified_badge}{ta_badge}</div>'
            f'</div>'
            f'</div>'
        )

    @classmethod
    def from_skill_result(cls, raw: dict) -> "SupplierCard":
        """
        Construct a ``SupplierCard`` from a raw supplier dict returned
        by ``AmazonSellerSkill``.

        Accepts both the canonical field names produced by the skill
        and common alternates so callers do not need to pre-normalise.
        """
        return cls(
            supplier_name   = raw.get("supplier_name",   raw.get("company_name",  "Unknown Supplier")),
            product_title   = raw.get("product_title",   raw.get("title",         "")),
            price_range     = raw.get("price_range",     raw.get("price",         "Price on request")),
            moq             = str(raw.get("min_order_qty", raw.get("moq",         "1"))),
            rating          = str(raw.get("rating",       raw.get("score",        "N/A")) or "N/A"),
            verified        = bool(raw.get("verified_supplier", raw.get("verified", False))),
            trade_assurance = bool(raw.get("trade_assurance", False)),
            url             = raw.get("url",             raw.get("link",          "")),
            demo_data       = bool(raw.get("demo_data",  False)),
        )


# ── CampaignCard ───────────────────────────────────────────────

@dataclass
class CampaignCard:
    """
    Typed representation of a single PPC keyword / campaign item.

    Attributes:
        keyword           The target keyword string.
        match_type        One of ``"Broad"``, ``"Phrase"``, or ``"Exact"``.
        suggested_bid     Display string for the bid, e.g. ``"$0.75"``.
        estimated_clicks  Estimated daily clicks as an integer.
    """

    keyword:          str = ""
    match_type:       str = "Broad"
    suggested_bid:    str = "$0.50"
    estimated_clicks: int = 0

    # Convenience colours aligned with Amazon console convention
    _MATCH_COLOURS: dict = field(
        default_factory=lambda: {
            "Broad":  "#f39c12",  # amber
            "Phrase": "#2980b9",  # blue
            "Exact":  "#27ae60",  # green
        },
        repr=False,
        compare=False,
    )

    def match_colour(self) -> str:
        """Return a hex colour string for the match type badge."""
        return self._MATCH_COLOURS.get(self.match_type, "#7f8c8d")

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dictionary of this card's fields."""
        return {
            "keyword":          self.keyword,
            "match_type":       self.match_type,
            "suggested_bid":    self.suggested_bid,
            "estimated_clicks": self.estimated_clicks,
        }

    def to_html_card(self) -> str:
        """Render a self-contained HTML card for Web UI use."""
        colour = self.match_colour()
        return (
            f'<div class="card campaign-card">'
            f'<div class="card-body">'
            f'<span class="card-keyword">{self.keyword}</span>'
            f'<div class="card-meta">'
            f'<span class="badge badge-match-type" style="background:{colour}">'
            f'{self.match_type}</span>'
            f'<span class="card-bid">Bid: {self.suggested_bid}</span>'
            f'<span class="card-clicks">'
            f'~{self.estimated_clicks} clicks/day</span>'
            f'</div>'
            f'</div>'
            f'</div>'
        )

    @classmethod
    def from_skill_result(cls, raw: dict) -> "CampaignCard":
        """
        Construct a ``CampaignCard`` from a raw keyword dict returned
        by ``AmazonSellerSkill`` PPC builder mode.

        Accepts field names from the Claude JSON response as well as
        common alternates.
        """
        try:
            clicks = int(raw.get("estimated_clicks", raw.get("clicks", 0)) or 0)
        except (ValueError, TypeError):
            clicks = 0

        return cls(
            keyword          = raw.get("keyword",       raw.get("term",         "")),
            match_type       = raw.get("match_type",    raw.get("matchType",    "Broad")),
            suggested_bid    = str(raw.get("suggested_bid", raw.get("bid",      "$0.50")) or "$0.50"),
            estimated_clicks = clicks,
        )
