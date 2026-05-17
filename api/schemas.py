# api/schemas.py
# ──────────────────────────────────────────────────────────────
# Pydantic schemas for REST API request/response shapes.
# ──────────────────────────────────────────────────────────────

from pydantic import BaseModel


class Paper(BaseModel):
    """A single paper result returned by GET /api/literature."""
    title:    str
    authors:  str = ""
    year:     str = ""
    abstract: str = ""
    source:   str
    url:      str = ""


class LiteratureResponse(BaseModel):
    """Response envelope for GET /api/literature."""
    query:  str
    count:  int
    papers: list[Paper]


class Product(BaseModel):
    """A single Amazon product result returned by GET /api/amazon."""
    title:  str
    price:  str = ""
    rating: str = ""
    asin:   str = ""
    url:    str = ""


class AmazonResponse(BaseModel):
    """Response envelope for GET /api/amazon."""
    query:    str
    count:    int
    products: list[Product]