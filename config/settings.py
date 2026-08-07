# config/settings.py
# ──────────────────────────────────────────────────────────────
# Central configuration for Agent Factory
# ──────────────────────────────────────────────────────────────

import os
import warnings
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

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
