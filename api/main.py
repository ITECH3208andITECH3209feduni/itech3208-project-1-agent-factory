# api/main.py
# ──────────────────────────────────────────────────────────────
# FastAPI app entrypoint.
# Run with:  uvicorn api.main:app --reload
# Then visit: http://localhost:8000/docs
# ──────────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import literature

app = FastAPI(
    title       = "Agent Factory API",
    description = "REST API for Agent Factory skills (literature, amazon).",
    version     = "0.1.0",
)

# Permissive CORS for dev — tighten before production.
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(literature.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}