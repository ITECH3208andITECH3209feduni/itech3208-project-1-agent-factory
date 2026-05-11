# components/amazon_cards.py
# ──────────────────────────────────────────────────────────────
# ProductCard dataclass — typed Amazon result for Web UI rendering
# PROJ-144 (Dilraj Singh)
# ──────────────────────────────────────────────────────────────

from dataclasses import dataclass, field


@dataclass
class ProductCard:
    """
    Typed representation of a single Amazon product result.

    score: 0-100 composite score based on:
        rating     × 40  (normalised 0-5 → 0-1)
        reviews    × 30  (log-normalised, cap 10,000)
        price      × 20  (inverse, cap $1000)
        availability × 10 (1.0=in stock, 0.5=limited, 0.0=out)
    """
    title:        str
    price:        str        = ""
    rating:       float      = 0.0
    review_count: int        = 0
    score:        int        = 0
    url:          str        = ""
    image_url:    str        = ""
    source:       str        = "amazon"
    availability: str        = "in_stock"
    bsr:          str        = ""
    category:     str        = ""

    def score_color(self, score: int | None = None) -> str:
        s = score if score is not None else self.score
        if s >= 70:
            return "green"
        elif s >= 40:
            return "amber"
        return "red"

    def to_dict(self) -> dict:
        return {
            "title":        self.title,
            "price":        self.price,
            "rating":       self.rating,
            "review_count": self.review_count,
            "score":        self.score,
            "score_color":  self.score_color(),
            "url":          self.url,
            "image_url":    self.image_url,
            "source":       self.source,
            "availability": self.availability,
            "bsr":          self.bsr,
            "category":     self.category,
        }

    def to_html_card(self) -> str:
        color = self.score_color()
        color_hex = {"green": "#27ae60", "amber": "#f39c12", "red": "#e74c3c"}[color]
        stars = "★" * int(self.rating) + "☆" * (5 - int(self.rating))
        price_display = self.price if self.price else "Price N/A"
        url_attr = f'href="{self.url}"' if self.url else 'href="#"'
        return f"""<div class="card product-card" data-score="{self.score}">
  <div class="card-score-badge" style="background:{color_hex}">{self.score}</div>
  <div class="card-body">
    <a {url_attr} target="_blank" class="card-title">{self.title}</a>
    <div class="card-meta">
      <span class="card-price">{price_display}</span>
      <span class="card-stars" title="{self.rating}/5">{stars}</span>
      <span class="card-reviews">({self.review_count:,} reviews)</span>
    </div>
    {f'<div class="card-bsr">BSR #{self.bsr} in {self.category}</div>' if self.bsr else ''}
  </div>
</div>"""

    @classmethod
    def from_skill_result(cls, raw: dict) -> "ProductCard":
        import math
        title        = raw.get("title", "Unknown Product")
        price_str    = raw.get("price", "")
        rating       = float(raw.get("rating", 0) or 0)
        review_count = int(raw.get("reviews", raw.get("review_count", 0)) or 0)
        url          = raw.get("url", raw.get("link", ""))
        image_url    = raw.get("image_url", raw.get("image", ""))
        bsr          = str(raw.get("bsr", raw.get("best_seller_rank", "")) or "")
        category     = raw.get("category", "")
        try:
            price_num = float(price_str.replace("$", "").replace(",", "").split()[0])
        except (ValueError, IndexError):
            price_num = 0.0
        avail_raw = str(raw.get("availability", "in stock")).lower()
        if "out" in avail_raw:
            avail_factor, availability = 0.0, "out_of_stock"
        elif "limited" in avail_raw or "only" in avail_raw:
            avail_factor, availability = 0.5, "limited"
        else:
            avail_factor, availability = 1.0, "in_stock"
        r_norm  = (rating / 5.0) * 40
        rv_norm = (math.log10(review_count + 1) / math.log10(10001)) * 30 if review_count > 0 else 0
        p_norm  = max(0.0, (1.0 - min(price_num, 1000) / 1000)) * 20 if price_num > 0 else 10
        a_norm  = avail_factor * 10
        score   = round(r_norm + rv_norm + p_norm + a_norm)
        return cls(title=title, price=price_str, rating=rating, review_count=review_count,
                   score=score, url=url, image_url=image_url, source="amazon",
                   availability=availability, bsr=bsr, category=category)
