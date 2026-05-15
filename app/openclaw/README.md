# app/openclaw — OpenClaw SDK Integration

## Overview

The `app/openclaw` package integrates the OpenClaw SDK into Agent Factory. It provides a query router that automatically classifies user queries and dispatches them to the correct skill (Amazon product research or Literature search), with automatic fallback to direct skill execution if the SDK is unavailable.

```
User query
    |
    v
classify(query)          # "amazon" or "literature"
    |
    v
route_query(query, wrapper)
    |
    +-- OpenClaw available --> wrapper.execute(skill, query)
    |
    +-- OpenClaw down      --> skill_registry handler directly
```

## Installation

Install the SDK alongside the project dependencies:

```bash
pip install -r requirements.txt
```

The `openclaw-sdk` package is included in `requirements.txt`. To install it standalone:

```bash
pip install openclaw-sdk
```

## Configuration

Copy `.env.example` to `.env` and set the following variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENCLAW_API_KEY` | Yes* | — | API key for the OpenClaw runtime |
| `OPENCLAW_TIMEOUT` | No | `30` | Seconds before an SDK call times out |
| `OPENCLAW_ENABLED` | No | `true` | Set to `false` to skip OpenClaw and use fallback directly |
| `PYTEST_RUNNING` | No | — | Set to `1` in test environments to use dummy key |

*Not required when `OPENCLAW_ENABLED=false` or `PYTEST_RUNNING=1`.

Validate config at startup:

```python
from app.openclaw.config import validate_config

config = validate_config()  # raises ValueError if OPENCLAW_API_KEY missing
```

## Usage

Basic usage with `route_query`:

```python
from app.openclaw.client import OpenClawWrapper
from app.openclaw.router import route_query

wrapper = OpenClawWrapper(api_key="your-key", timeout=30)
wrapper.connect()

# Automatically routes to the correct skill
result = route_query("best laptop under $1000", wrapper)
print(result["result"])

result = route_query("papers on transformer architecture", wrapper)
print(result["result"])
```

Using the high-level agent entry point (recommended):

```python
from app.openclaw.client import OpenClawWrapper
from app.agent import run_query

wrapper = OpenClawWrapper(api_key="your-key")
wrapper.connect()

result = run_query("best wireless earbuds", wrapper)
print(result)
```

Run the smoke test to verify everything works:

```bash
python scripts/test_openclaw.py
```

## Skills Registry

The registry maps skill names to their handlers. By default `amazon` and `literature` are registered.

List available skills:

```python
from app.openclaw.skills_registry import list_skills, get_skill

print(list_skills())  # ['amazon', 'literature']

skill = get_skill("amazon")
print(skill["description"])
```

Register a custom skill at runtime:

```python
from app.openclaw.skills_registry import register_skill

def my_news_handler(query: str):
    # fetch and return news results
    return {"result": f"News results for: {query}"}

register_skill(
    name="news",
    handler=my_news_handler,
    description="Search latest news articles",
    timeout=20,
)
```

## Fallback Behaviour

If the OpenClaw SDK raises any exception, the system automatically falls back to calling the skill handler directly. The `with_fallback` decorator makes any function fallback-safe:

```python
from app.openclaw.fallback import with_fallback, FALLBACK_COUNT
from skills.amazon import AmazonSkill

_skill = AmazonSkill()

def direct_search(query):
    return {"result": _skill.run(query).summary, "skill": "amazon"}

@with_fallback(direct_search)
def openclaw_search(query):
    return wrapper.execute("amazon", query)

# If wrapper.execute fails, direct_search is called automatically
result = openclaw_search("best laptop")

# Check how many times fallback was used this session
print(f"Fallback used {FALLBACK_COUNT} times")
```

Fallback is also triggered automatically when `OPENCLAW_ENABLED=false` in `.env`.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ValueError: OPENCLAW_API_KEY is not set` | Missing env var | Add `OPENCLAW_API_KEY=your-key` to `.env`, or set `OPENCLAW_ENABLED=false` to skip OpenClaw |
| `ConnectionError: OpenClaw is down` | SDK cannot reach the runtime | Check your network, verify the API key is valid. The fallback will handle queries automatically. |
| `KeyError: Skill 'X' not found` | Skill name not in registry | Run `list_skills()` to see available names. Register the skill with `register_skill()` if needed. |
| `ModuleNotFoundError: No module named 'openclaw'` | SDK not installed | Run `pip install openclaw-sdk` or `pip install -r requirements.txt` |
| All tests fail in CI | Missing env vars in CI | Set `PYTEST_RUNNING=1` and `OPENCLAW_ENABLED=false` in your CI environment variables |

Check fallback is working:

```python
from app.openclaw.fallback import FALLBACK_COUNT
print(f"Fallback triggered {FALLBACK_COUNT} times this session")
```
