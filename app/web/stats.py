"""
app.web.stats — metric providers for the dashboard (PROJ-437).

The dashboard shell has to render before the data it eventually shows exists.
Contacts live behind PROJ-417 (which waits on Dhiman's data contract PROJ-404)
and reminders behind Dilraj's store (PROJ-422).

So a metric is explicit about whether it has a source. A pending metric reports
`available=False` and names its blocker; it does NOT report 0. A zero that means
"no source yet" is indistinguishable from a measured zero, and a dashboard that
quietly shows 0 contacts is worse than one that says the store isn't wired up.

Each metric is a small provider function. When a store lands, replace the
provider body — the tile, the API, and the tests need no change.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

log = logging.getLogger("agent_factory.stats")


@dataclass
class Metric:
    """One stat tile's worth of data."""

    key:   str
    label: str                              # sentence case, no trailing colon
    value: int | float | None = None
    unit:  str = ""
    # Delta is optional and only meaningful against a named period. A signed
    # number with no period attached tells the reader nothing.
    delta:        float | None = None
    delta_period: str = ""
    # True when up is good; drives the delta's colour direction.
    higher_is_better: bool = True
    available:  bool = True
    blocked_by: str = ""                    # e.g. "PROJ-422"
    note:       str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pending(key: str, label: str, blocked_by: str, note: str) -> Metric:
    return Metric(
        key=key, label=label, value=None,
        available=False, blocked_by=blocked_by, note=note,
    )


# ── Providers that work today ─────────────────────────────────
def skills_registered() -> Metric:
    """Count of valid skill manifests. Real data — the registry exists."""
    try:
        from skills.manifest_loader import discover_manifests

        manifests = discover_manifests(strict=False)
        valid = [m for m in manifests if not m.get("_errors")]
        broken = len(manifests) - len(valid)
        return Metric(
            key="skills_registered",
            label="Skills registered",
            value=len(valid),
            note=f"{broken} manifest(s) failed to load" if broken else "",
        )
    except Exception as exc:  # noqa: BLE001
        # A broken provider must not take the dashboard down with it.
        log.warning("skills_registered failed: %s", exc)
        return Metric(
            key="skills_registered", label="Skills registered",
            available=False, note=f"provider error: {exc}",
        )


def queries_run() -> Metric:
    """Total queries in local memory. Real data — agent/memory.py exists."""
    try:
        from agent.memory import Memory

        stats = Memory().stats()
        return Metric(
            key="queries_run",
            label="Queries run",
            value=int(stats.get("total_queries", 0)),
            note="since memory was last cleared",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("queries_run failed: %s", exc)
        return Metric(
            key="queries_run", label="Queries run",
            available=False, note=f"provider error: {exc}",
        )


# ── Providers waiting on other people's tickets ───────────────
def contacts_total() -> Metric:
    return _pending(
        "contacts_total", "Contacts",
        "PROJ-417",
        "Contacts store not built. Waits on the org/contact data contract (PROJ-404).",
    )


def reminders_upcoming() -> Metric:
    return _pending(
        "reminders_upcoming", "Upcoming reminders",
        "PROJ-422",
        "Reminders store not built (Reminders Engine, PROJ-395).",
    )


def reminders_sent() -> Metric:
    return _pending(
        "reminders_sent", "Reminders sent",
        "PROJ-422",
        "Send history not available until the reminders store lands.",
    )


# ── Registry ──────────────────────────────────────────────────
# Order is the display order of the KPI row. The hero metric comes first.
PROVIDERS: list[Callable[[], Metric]] = [
    reminders_upcoming,     # hero — what the epic says the page leads with
    contacts_total,
    reminders_sent,
    skills_registered,
    queries_run,
]

# Which metric is rendered as the hero figure. Exactly one per view.
HERO_KEY = "reminders_upcoming"


def collect() -> list[Metric]:
    """Run every provider. A failing provider degrades to unavailable."""
    out: list[Metric] = []
    for provider in PROVIDERS:
        try:
            out.append(provider())
        except Exception as exc:  # noqa: BLE001
            log.exception("provider %s raised", getattr(provider, "__name__", "?"))
            out.append(
                Metric(
                    key=getattr(provider, "__name__", "unknown"),
                    label=getattr(provider, "__name__", "unknown").replace("_", " ").capitalize(),
                    available=False,
                    note=f"provider error: {exc}",
                )
            )
    return out


def summary() -> dict[str, Any]:
    """Payload for GET /api/stats and the dashboard template."""
    metrics = collect()
    return {
        "hero": HERO_KEY,
        "available_count": sum(1 for m in metrics if m.available),
        "pending_count": sum(1 for m in metrics if not m.available),
        "metrics": [m.to_dict() for m in metrics],
    }
