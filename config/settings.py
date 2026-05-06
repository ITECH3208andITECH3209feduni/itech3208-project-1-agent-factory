# config/settings.py
# ──────────────────────────────────────────────────────────────
# Central configuration for Agent Factory
# ──────────────────────────────────────────────────────────────

import os
import warnings
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# ── Resolve base directory so all paths work regardless of cwd ─
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Claude / Anthropic ─────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")
CLAUDE_MODEL      = "claude-sonnet-4-6"   # faster + cheaper than opus

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
ARXIV_BASE_URL          = "https://export.arxiv.org/api/query"   # HTTPS — avoids 403
SEMANTIC_SCHOLAR_URL    = "https://api.semanticscholar.org/graph/v1/paper/search"
PUBMED_SEARCH_URL       = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL        = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# ── Amazon scraping ────────────────────────────────────────────
AMAZON_BASE_URL   = "https://www.amazon.com"
AMAZON_HEADERS    = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# ── Memory / persistence ───────────────────────────────────────
MEMORY_FILE       = os.path.join(_BASE_DIR, "outputs", "memory.json")
MAX_HISTORY_ITEMS = 50    # keep last N queries in memory

# ── Output ─────────────────────────────────────────────────────
OUTPUT_DIR        = os.path.join(_BASE_DIR, "outputs")
DEFAULT_FORMAT    = "markdown"   # "markdown" | "json"
