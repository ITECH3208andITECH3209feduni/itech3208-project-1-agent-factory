# Agent Factory — Web UI

Browser-based chat interface for the Agent Factory research assistant.
Built with **FastAPI** + plain HTML/CSS/JS (no frontend framework needed).

## Overview

The Web UI wraps the existing CLI agent in a REST API and serves a dark-themed chat interface at `http://localhost:8000`.

- Type a query → agent routes to Amazon, Literature, Integrity, or Seller skill automatically
- Results appear as rich cards (product cards with score badges, paper cards with citation counts, supplier/campaign cards)
- Chat history loads on page open, scoped to the logged-in user (PROJ-349)
- Login required for `/query`, `/history`, `/receptionist`, `/calendar/ics`, `/kb/*`

## Install

```bash
pip install -r requirements.txt -r requirements_web.txt
```

## Run

```bash
python -m app.web_ui.main
```

Then open **http://localhost:8000** in your browser.

For hot-reload during development:
```bash
uvicorn app.web_ui.main:app --reload --port 8000
```

## Endpoints

| Method | Path               | Description                                              | Auth |
|--------|--------------------|------------------------------------------------------------|------|
| GET    | `/`                | Serves `static/index.html` (chat UI)                       | –    |
| GET    | `/literature`      | Serves `static/literature.html` (standalone search page)   | –    |
| POST   | `/auth/register`   | Create an account                                           | –    |
| POST   | `/auth/login`      | Log in, sets session cookie                                 | –    |
| POST   | `/auth/logout`     | Log out                                                      | –    |
| GET    | `/auth/me`         | Current logged-in username                                   | –    |
| POST   | `/query`           | Run a research/shopping query, returns response + cards      | ✓    |
| GET    | `/history`         | Last 20 queries from the logged-in user's own memory         | ✓    |
| POST   | `/literature`      | Dedicated literature search (PROJ-92–94)                     | –    |
| POST   | `/amazon`          | Dedicated Amazon product search (PROJ-166)                   | –    |
| POST   | `/integrity`       | Academic integrity check — AI detection + plagiarism (PROJ-184–186) | –    |
| POST   | `/seller`          | Amazon seller tools — suppliers/PPC/profit (PROJ-187–190)     | –    |
| POST   | `/export`          | Export a result to PDF/Excel (PROJ-191)                       | –    |
| GET    | `/export/download` | Download a previously exported file                           | –    |
| POST   | `/receptionist`    | AI Receptionist — FAQ, escalation, booking (PROJ-195, 209-218) | ✓    |
| GET    | `/calendar/ics`    | Download a booked appointment as a `.ics` file (PROJ-294-298)  | ✓    |
| POST   | `/kb/upload`       | Upload a document to your Knowledge Base (PROJ-279-283)       | ✓    |
| GET    | `/kb/list`         | List your uploaded Knowledge Base documents                    | ✓    |
| DELETE | `/kb/{id}`         | Delete one of your Knowledge Base documents                    | ✓    |
| GET    | `/kb/search`       | Keyword search over your own Knowledge Base documents          | ✓    |
| GET    | `/status`          | Health check — `{"status": "ok", "agent": "ready"}`            | –    |

### POST /query

**Request:**
```json
{ "query": "best wireless earbuds under $50" }
```

**Response:**
```json
{
  "response": "Here are the top products I found...",
  "cards": [ { "title": "...", "price": "$39.99", "score": 78, ... } ],
  "type": "amazon"
}
```

## File Structure

```
app/web_ui/
  main.py                FastAPI app + static mount + root/literature routes
  routes.py               /query, /literature, /amazon, /integrity, /seller, /export, /history, /status
  auth_routes.py           /auth/register, /auth/login, /auth/logout, /auth/me (PROJ-349-353)
  receptionist_routes.py   /receptionist (PROJ-195, 209-218)
  calendar_routes.py       /calendar/ics (PROJ-294-298)
  kb_routes.py             /kb/upload, /kb/list, /kb/{id}, /kb/search (PROJ-279-283)
  README.md                This file

skills/
  academic_integrity.py   AI detection + plagiarism scanner (PROJ-184-186)
  amazon_seller.py         Alibaba/PPC/profit tools (PROJ-187-190)
  export.py                PDF/Excel export (PROJ-191)

components/
  amazon_cards.py      ProductCard dataclass + score_color() + to_html_card()
  literature_cards.py  PaperCard dataclass + truncate_abstract() + to_html_card()
  integrity_cards.py   IntegrityCard dataclass
  seller_cards.py       SupplierCard, CampaignCard dataclasses

static/
  index.html          Chat UI shell (all tabs, including Knowledge Base and Integrity)
  literature.html      Standalone literature search page
  css/style.css        Dark theme (CSS variables)
  js/app.js            sendMessage(), loadHistory(), renderCards(), KB + integrity handlers

requirements_web.txt  fastapi, uvicorn, python-multipart, jinja2
```
