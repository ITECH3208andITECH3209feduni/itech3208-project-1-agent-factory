# Agent Factory — Web UI

Browser-based chat interface for the Agent Factory research assistant.
Built with **FastAPI** + plain HTML/CSS/JS.

## Install

```bash
pip install -r requirements_web.txt
```

## Run

```bash
python -m app.web_ui.main
```

Open **http://localhost:8000**

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Chat UI (index.html) |
| POST | `/query` | Run query, returns `{response, cards, type}` |
| GET | `/history` | Last 20 queries |
| GET | `/status` | `{status: "ok", agent: "ready"}` |

## File Structure

```
app/web_ui/main.py       FastAPI entry point
app/web_ui/routes.py     API endpoints
components/amazon_cards.py    ProductCard dataclass
components/literature_cards.py PaperCard dataclass
static/index.html        Chat UI
static/css/style.css     Dark theme
static/js/app.js         sendMessage, loadHistory, renderCards
requirements_web.txt     fastapi uvicorn python-multipart jinja2
```
