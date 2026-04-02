# config/settings.py
# ──────────────────────────────────────────────────────────────
# Central configuration for Agent Factory
# ──────────────────────────────────────────────────────────────

import os

# ── Claude / Anthropic ─────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")
CLAUDE_MODEL      = "claude-opus-4-6"   # swap to claude-haiku-4-5-20251001 for speed

# ── Agent behaviour ────────────────────────────────────────────
MAX_RESULTS       = 10     # max items returned per skill call
REQUEST_TIMEOUT   = 15     # seconds before HTTP requests time out
MAX_RETRIES       = 3      # retry attempts on network failure

# ── Literature search ──────────────────────────────────────────
ARXIV_BASE_URL          = "http://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_URL    = "https://api.semanticscholar.org/graph/v1/paper/search"
PUBMED_SEARCH_URL       = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL        = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

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
