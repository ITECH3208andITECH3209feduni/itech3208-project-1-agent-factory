# config/settings.py
# ──────────────────────────────────────────────────────────────
# Central configuration for Agent Factory
# ──────────────────────────────────────────────────────────────

import os
import warnings
from pathlib import Path

from dotenv import load_dotenv

# Project root — resolved from this file, not the caller's cwd, so config
# loads identically no matter where the process was launched from (PROJ-380).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH     = PROJECT_ROOT / ".env"

# override=True so the committed .env is authoritative (PROJ-381).
# Without it, a stale exported shell variable silently beats the file the
# developer just edited — which cost us real debugging time in Sprint 2.
load_dotenv(dotenv_path=ENV_PATH, override=True)

# ── Claude / Anthropic ─────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")
CLAUDE_MODEL      = "claude-opus-4-6"   # swap to claude-haiku-4-5-20251001 for speed

# Warn loudly if API key is still the placeholder
if ANTHROPIC_API_KEY == "YOUR_API_KEY_HERE":
    warnings.warn(
        "\n\n⚠️  ANTHROPIC_API_KEY not set!\n"
        "   Create a .env file in the project root:\n"
        "   echo 'ANTHROPIC_API_KEY=sk-ant-api03-...' > .env\n"
        "   Get your key at: https://console.anthropic.com\n"
        "   Claude AI features (synthesis, sentiment, opportunity scoring) will be disabled.\n",
        UserWarning,
        stacklevel=2,
    )

# ── Agent behaviour ────────────────────────────────────────────
MAX_RESULTS       = 10     # max items returned per skill call
REQUEST_TIMEOUT   = 15     # seconds before HTTP requests time out
MAX_RETRIES       = 3      # retry attempts on network failure

# ── Literature search ──────────────────────────────────────────
ARXIV_BASE_URL              = "http://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_URL        = "https://api.semanticscholar.org/graph/v1/paper/search"
PUBMED_SEARCH_URL           = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL            = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Semantic Scholar API key (PROJ-379).
# Register at https://www.semanticscholar.org/product/api-key
# S2_API_KEY is the canonical name; SEMANTIC_SCHOLAR_API_KEY is still read so
# existing .env files keep working.
S2_API_KEY = os.environ.get("S2_API_KEY") or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")

# Backwards-compatible alias — existing imports refer to this name.
SEMANTIC_SCHOLAR_API_KEY = S2_API_KEY

# Client-side rate limit for Semantic Scholar (PROJ-379).
# The keyed tier is 100 requests / 5 minutes. Without a key the public tier is
# roughly 1 req/s, so we fall back to a much smaller budget over the same window.
S2_RATE_LIMIT_REQUESTS = int(os.environ.get("S2_RATE_LIMIT_REQUESTS", "100" if S2_API_KEY else "20"))
S2_RATE_LIMIT_PERIOD   = float(os.environ.get("S2_RATE_LIMIT_PERIOD", "300"))

# Give up rather than block forever if the bucket is exhausted.
S2_RATE_LIMIT_TIMEOUT  = float(os.environ.get("S2_RATE_LIMIT_TIMEOUT", "60"))

# ── Amazon scraping ────────────────────────────────────────────
AMAZON_BASE_URL   = "https://www.amazon.com"
AMAZON_HEADERS    = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Memory / persistence ───────────────────────────────────────
MEMORY_FILE       = "outputs/memory.json"
MAX_HISTORY_ITEMS = 50    # keep last N queries in memory

# ── Output ─────────────────────────────────────────────────────
OUTPUT_DIR        = "outputs"
DEFAULT_FORMAT    = "markdown"   # "markdown" | "json"

# ── Sprint 3: Telegram ─────────────────────────────────────────
# Bot token from @BotFather. Required only when the Telegram channel runs.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# ── Sprint 3: Google Calendar ──────────────────────────────────
# Path to the OAuth client secrets JSON downloaded from Google Cloud Console.
# A path, never the credential body — keeps the secret out of the environment
# block, which leaks into `docker inspect` and crash reports.
GOOGLE_CALENDAR_CREDENTIALS = os.environ.get("GOOGLE_CALENDAR_CREDENTIALS", "")

# Where the user's OAuth token is cached after the consent flow.
GOOGLE_CALENDAR_TOKEN_PATH = os.environ.get(
    "GOOGLE_CALENDAR_TOKEN_PATH", str(PROJECT_ROOT / "store" / "google_calendar_token.json")
)

# ── Sprint 3: ChromaDB ─────────────────────────────────────────
# On-disk vector store location. Defaults inside the project so a fresh
# clone works without configuration; override to a volume in Docker.
CHROMADB_PATH       = os.environ.get("CHROMADB_PATH", str(PROJECT_ROOT / "store" / "chromadb"))
CHROMADB_COLLECTION = os.environ.get("CHROMADB_COLLECTION", "agent_factory")

# ── Sprint 3: Web API auth ─────────────────────────────────────
# Signing secret for session tokens issued by the FastAPI layer.
JWT_SECRET    = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_TTL_SEC   = int(os.environ.get("JWT_TTL_SEC", "86400"))


# ── Environment validation (PROJ-381) ──────────────────────────
def validate_env(strict: bool = False) -> list[str]:
    """
    Check the environment and return a list of human-readable problems.

    Only ANTHROPIC_API_KEY is required for the core CLI. Everything else is
    feature-gated: its absence disables one capability rather than breaking
    startup, so we report it without failing.

    strict=True raises RuntimeError instead of returning, for use in
    deployment health checks where a half-configured process is worse than
    no process.
    """
    problems: list[str] = []

    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "YOUR_API_KEY_HERE":
        problems.append("ANTHROPIC_API_KEY is not set — Claude features are disabled.")

    if not S2_API_KEY:
        problems.append(
            "S2_API_KEY is not set — Semantic Scholar is limited to "
            f"{S2_RATE_LIMIT_REQUESTS} requests / {S2_RATE_LIMIT_PERIOD:.0f}s."
        )

    if not BOT_TOKEN:
        problems.append("BOT_TOKEN is not set — the Telegram channel will not start.")

    if GOOGLE_CALENDAR_CREDENTIALS and not Path(GOOGLE_CALENDAR_CREDENTIALS).exists():
        problems.append(
            f"GOOGLE_CALENDAR_CREDENTIALS points at a missing file: {GOOGLE_CALENDAR_CREDENTIALS}"
        )
    elif not GOOGLE_CALENDAR_CREDENTIALS:
        problems.append("GOOGLE_CALENDAR_CREDENTIALS is not set — calendar features are disabled.")

    # A blank signing secret means every token validates. Worse than no auth,
    # because it looks like auth.
    if not JWT_SECRET:
        problems.append("JWT_SECRET is not set — the web API must not be exposed publicly.")
    elif len(JWT_SECRET) < 32:
        problems.append(
            f"JWT_SECRET is only {len(JWT_SECRET)} characters; use at least 32 "
            "(python -c 'import secrets; print(secrets.token_urlsafe(48))')."
        )

    if strict and problems:
        raise RuntimeError("Environment validation failed:\n  - " + "\n  - ".join(problems))

    return problems
