# Paper Search Skill

Routes academic literature queries to `LiteratureSkill` in `skills/literature.py`.

## Trigger phrases

| Pattern | Mode activated |
|---|---|
| "find papers on X", "research on X" | Standard search (arXiv + Semantic Scholar) |
| "synthesise papers on X", "overview of X" | Multi-paper synthesis (PROJ-92) |
| "research gaps in X", "future work on X" | Gap analysis (PROJ-93) |
| "citations for X", "who cited X" | Forward citation lookup (PROJ-94) |

## Sources queried

- **arXiv** — preprints via `export.arxiv.org/api/query` (HTTPS)
- **Semantic Scholar** — citation-rich metadata via `api.semanticscholar.org/graph/v1`
- **PubMed** — medical/clinical queries only (triggered by keywords: medicine, clinical, drug, disease, patient, trial)

## Output fields (per paper)

```
title, authors, year, abstract (≤400 chars), link, source, citations, paper_id
```

## Claude-powered modes

| Mode | Model | Max tokens |
|---|---|---|
| Multi-paper synthesis | `claude-haiku-4-5-20251001` | 600 |
| Research gap analysis | `claude-haiku-4-5-20251001` | 500 |
| Result summarisation (orchestrator) | `claude-sonnet-4-6` | 200 |

Synthesis and gap modes are silently skipped if `ANTHROPIC_API_KEY` is not set.

## Rate limiting

All HTTP calls go through `_retry_get`: 3 attempts, exponential backoff (2 s / 4 s / 8 s) on 429 or transient errors.
