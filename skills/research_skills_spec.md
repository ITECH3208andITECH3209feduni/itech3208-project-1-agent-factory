# Research Skills — Architecture Spec

Describes the design contract for all research skills in Agent Factory.

## Skill interface

Every skill inherits `BaseSkill` (`skills/base_skill.py`) and must implement:

```python
def run(self, query: str) -> SkillResult: ...
```

`BaseSkill.__call__` wraps `run`, records `duration_sec`, and catches unhandled exceptions into a failed `SkillResult`.

## SkillResult contract

```python
@dataclass
class SkillResult:
    skill_name:   str
    query:        str
    success:      bool
    results:      list[dict]   # raw paper/product dicts
    summary:      str          # human-readable answer
    error:        str          # non-empty on failure
    metadata:     dict         # skill-specific extra fields
    duration_sec: float
```

## Implemented skills

| Class | File | Skill name |
|---|---|---|
| `LiteratureSkill` | `skills/literature.py` | `"literature"` |
| `AmazonSkill` | `skills/amazon.py` | `"amazon"` |

## Routing

`Orchestrator._route()` (`agent/orchestrator.py`) uses a two-stage approach:

1. **Keyword fast-path** — counts hits against `amazon_keywords` / `literature_keywords` sets; routes immediately if unambiguous.
2. **Claude fallback** — sends a structured routing prompt to `claude-sonnet-4-6`; returns `SKILL: literature`, `SKILL: amazon`, or `CLARIFY: <question>`.

## Literature pipeline (Sprint 2)

```
query
  └─ _search_arxiv()           ← arXiv Atom feed
  └─ _search_semantic_scholar() ← S2 graph API
  └─ _search_pubmed()           ← PubMed (medical only)
       │
       ├─ [synthesis trigger] → _synthesise_papers()  → claude-haiku-4-5-20251001
       ├─ [gap trigger]       → _find_research_gaps() → claude-haiku-4-5-20251001
       └─ [citation trigger]  → _run_citation_lookup() → S2 citations endpoint
```

## PaperCard

`components/literature_cards.py` — typed view model consumed by the Web UI.

```python
PaperCard.from_skill_result(raw: dict) -> PaperCard
PaperCard.to_dict()      -> dict   # JSON-safe, used in /query response
PaperCard.to_html_card() -> str    # rendered HTML card for UI
```

## Adding a new research skill

1. Create `skills/<name>.py`, subclass `BaseSkill`, implement `run()`.
2. Add an entry to `SKILLS` dict in `agent/orchestrator.py`.
3. Extend `_quick_route` keyword sets and the `ROUTING_PROMPT` available-skills list.
4. Add a `<name>.skill.md` in `skills/` documenting trigger phrases and output fields.
