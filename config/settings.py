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
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")
CLAUDE_MODEL       = "claude-sonnet-4-6"         # orchestrator routing + result summarisation
CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"  # synthesis engine — fast, low cost per paper batch

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
MEMORY_DB         = os.environ.get("MEMORY_DB") or os.path.join(_BASE_DIR, "outputs", "memory.db")
MEMORY_FILE       = os.path.join(_BASE_DIR, "outputs", "memory.json")  # kept for one-shot migration
MAX_HISTORY_ITEMS = 50    # keep last N queries in memory

# ── Auth (Web UI login — PROJ-349) ──────────────────────────────
AUTH_DB = os.environ.get("AUTH_DB") or os.path.join(_BASE_DIR, "outputs", "auth.db")

# Secret used to sign session cookie tokens (agent/auth.py). Prefer
# setting AUTH_SECRET_KEY in .env for real deployments — a key that
# changes on every restart invalidates every logged-in session. If it's
# not set, we generate one on first run and persist it to
# outputs/.auth_secret so restarts on the same machine keep working.
AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "")
if not AUTH_SECRET_KEY:
    _secret_path = os.path.join(_BASE_DIR, "outputs", ".auth_secret")
    if os.path.exists(_secret_path):
        with open(_secret_path, "r", encoding="utf-8") as _fh:
            AUTH_SECRET_KEY = _fh.read().strip()
    if not AUTH_SECRET_KEY:
        import secrets as _secrets

        AUTH_SECRET_KEY = _secrets.token_hex(32)
        os.makedirs(os.path.dirname(_secret_path), exist_ok=True)
        with open(_secret_path, "w", encoding="utf-8") as _fh:
            _fh.write(AUTH_SECRET_KEY)
        warnings.warn(
            "\n\n⚠️  AUTH_SECRET_KEY not set — generated one and saved it to "
            f"{_secret_path}.\n"
            "   Set AUTH_SECRET_KEY in .env for real deployments — otherwise "
            "logged-in sessions won't survive a move to a new machine.\n",
            UserWarning,
            stacklevel=2,
        )

# ── AI Receptionist (PROJ-195 epic / PROJ-209-218) ──────────────
# Reuses the exact same Google Calendar service-account credentials
# already configured for the NanoClaw Telegram bot's booking feature
# (see .env — GOOGLE_CALENDAR_KEY_PATH / GOOGLE_CALENDAR_ID) so there's
# nothing new to set up to get appointment booking working here too.
GOOGLE_CALENDAR_KEY_PATH = os.environ.get("GOOGLE_CALENDAR_KEY_PATH", "")
GOOGLE_CALENDAR_ID       = os.environ.get("GOOGLE_CALENDAR_ID", "")
TIMEZONE                 = os.environ.get("TIMEZONE", "Australia/Melbourne")

# Keyword-matched FAQ knowledge base (stdlib-only placeholder for the
# ChromaDB semantic search called for in PROJ-214-218 — swap in real
# embeddings + vector search once there's a real document corpus to
# index; a JSON keyword matcher isn't a substitute for that long-term).
FAQ_DATA_PATH      = os.environ.get("FAQ_DATA_PATH") or os.path.join(_BASE_DIR, "config", "faq_seed.json")
FAQ_MIN_SCORE      = 0.3    # Jaccard token-overlap threshold to accept a match

# Human escalation log (PROJ-195: "human escalation")
ESCALATION_LOG     = os.environ.get("ESCALATION_LOG") or os.path.join(_BASE_DIR, "outputs", "escalations.jsonl")

# ── Knowledge Base management tab (PROJ-279-283) ────────────────
# Per-user uploaded documents — see agent/kb_store.py for the honest
# scope note (keyword search, not ChromaDB; text files only).
KB_DB              = os.environ.get("KB_DB") or os.path.join(_BASE_DIR, "outputs", "kb.db")

# ── Output ─────────────────────────────────────────────────────
OUTPUT_DIR        = os.path.join(_BASE_DIR, "outputs")
DEFAULT_FORMAT    = "markdown"   # "markdown" | "json"
