"""
app.openclaw.router — Query classifier and skill dispatcher.
"""

from app.openclaw.client import OpenClawWrapper
from app.openclaw.skills_registry import get_skill

AMAZON_KEYWORDS = {
    "buy", "product", "price", "review", "compare", "amazon",
    "best", "cheap", "deal", "shop", "purchase", "rating",
    "under $", "budget", "affordable", "recommend", "sale",
}

LITERATURE_KEYWORDS = {
    "paper", "research", "study", "academic", "arxiv", "journal",
    "cite", "citation", "literature", "article", "author", "findings",
    "meta-analysis", "systematic review", "pubmed", "science", "experiment",
}


def classify(query: str) -> str:
    """
    Classify a query as 'amazon' or 'literature' based on keyword matching.
    Defaults to 'literature' when ambiguous or no keywords match.
    """
    q_lower = query.lower()

    amazon_score = sum(1 for kw in AMAZON_KEYWORDS if kw in q_lower)
    literature_score = sum(1 for kw in LITERATURE_KEYWORDS if kw in q_lower)

    if amazon_score > literature_score:
        return "amazon"
    return "literature"


def route_query(query: str, wrapper: OpenClawWrapper) -> dict:
    """
    Classify the query, dispatch to the correct skill via wrapper, return result.
    """
    skill_name = classify(query)
    get_skill(skill_name)  # validates skill exists, raises KeyError if not
    return wrapper.execute(skill_name, query)
