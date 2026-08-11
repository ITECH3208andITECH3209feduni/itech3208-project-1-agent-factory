# services/amazon_service.py
# ──────────────────────────────────────────────────────────────
# Amazon sub-agent microservice (PROJ-244..248)
# Wraps AmazonSkill + AmazonSellerSkill.
# Supports both Dapr service invocation (POST /invoke) and
# Dapr pub/sub (topic "amazon-queries" on the redis pubsub component).
# ──────────────────────────────────────────────────────────────

import logging

from fastapi import FastAPI
from pydantic import BaseModel

from skills.amazon import AmazonSkill
from skills.amazon_seller import AmazonSellerSkill

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("amazon-agent")

PUBSUB_NAME = "pubsub"
TOPIC = "amazon-queries"

product_skill = AmazonSkill()
seller_skill = AmazonSellerSkill()

app = FastAPI(title="amazon-agent")

SELLER_HINTS = {
    "alibaba", "supplier", "ppc", "campaign", "sponsored",
    "profit", "margin", "acos", "bsr", "wholesale", "manufacturer",
}


class Query(BaseModel):
    query: str
    mode: str | None = None  # "product" | "seller" | None (auto)


def pick_skill(query: str, mode: str | None):
    """Route to the seller tools when the query looks like seller work."""
    if mode == "seller":
        return seller_skill
    if mode == "product":
        return product_skill
    q = query.lower()
    return seller_skill if any(h in q for h in SELLER_HINTS) else product_skill


# ── Dapr pub/sub subscription ──────────────────────────────────
@app.get("/dapr/subscribe")
def subscribe():
    """Dapr calls this on startup to discover our topic subscriptions."""
    return [
        {
            "pubsubname": PUBSUB_NAME,
            "topic": TOPIC,
            "route": "/events/amazon-query",
        }
    ]


@app.post("/events/amazon-query")
async def handle_event(event: dict):
    """
    Handle a CloudEvent delivered by Dapr on the amazon-queries topic.
    Returning 200 acknowledges the message; Dapr retries on failure.
    """
    data = event.get("data") or {}
    query = data.get("query", "")
    if not query:
        log.warning("event with no query, dropping: %s", event.get("id"))
        return {"status": "DROP"}

    skill = pick_skill(query, data.get("mode"))
    result = skill(query)
    log.info("pubsub handled %r via %s -> success=%s", query, skill.name, result.success)
    return {"status": "SUCCESS"}


# ── Service invocation ─────────────────────────────────────────
@app.get("/healthz")
def healthz():
    return {"status": "ok", "skill": "amazon", "skills": ["amazon", "amazon_seller"]}


@app.post("/invoke")
def invoke(body: Query):
    skill = pick_skill(body.query, body.mode)
    return skill(body.query).to_dict()