# Agent Factory — Web UI

Browser-based chat interface for the Agent Factory research assistant.
Built with **FastAPI** + plain HTML/CSS/JS (no frontend framework needed).

## Overview

The Web UI wraps the existing CLI agent in a REST API and serves a dark-themed chat interface at `http://localhost:8000`.

- Type a query → agent routes to Amazon or Literature skill automatically
- Results appear as rich cards (product cards with score badges, paper cards with citation counts)
- Chat history loads on page open

## Install

```bash
pip install -r requirements_web.txt
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

| Method | Path       | Description                                      |
|--------|------------|--------------------------------------------------|
| GET    | `/`        | Serves `static/index.html` (chat UI)            |
| POST   | `/query`   | Run a research query, returns response + cards   |
| GET    | `/history` | Last 20 queries from session memory             |
| GET    | `/status`  | Health check — `{"status": "ok", "agent": "ready"}` |
