"""Shared utilities for rendering a lineup spin into template-ready data."""
from __future__ import annotations

from itertools import combinations
from typing import Any

from ..models import BOOLEAN_PREFERENCE_DEFINITIONS, LineupSpin


def build_spin_display(spin: LineupSpin) -> dict[str, Any]:
    """Convert a LineupSpin into a flat dict ready for Jinja2 templates."""
    snapshot = spin.solution_snapshot or {}
    config = spin.config_snapshot or {}
    status = snapshot.get("status", "UNKNOWN")

    if status not in ("OPTIMAL", "FEASIBLE"):
        return {"solved": False, "status": status, "config": config}

    players: list[str] = snapshot.get("players", [])
    periods_per_half: list[int] = snapshot.get("periods_per_half", [0, 0])
    period_times: list[str] = snapshot.get("period_start_times", [])
    player_periods: list[dict[str, Any]] = snapshot.get("player_periods", [])

    # Period rows
    all_rows = []
    for i, time in enumerate(period_times):
        on = sorted(pp["player"] for pp in player_periods if pp["on"][i])
        off = sorted(pp["player"] for pp in player_periods if not pp["on"][i])
        all_rows.append({"period": i + 1, "time": time, "on": on, "off": off})

    # Per-player summary
    summary = sorted(
        [
            {
                "player": pp["player"],
                "on_count": sum(pp["on"]),
                "off_count": len(pp["on"]) - sum(pp["on"]),
            }
            for pp in player_periods
        ],
        key=lambda r: (-r["on_count"], r["player"]),
    )

    # Co-play pair stats
    pair_counts: dict[tuple[str, str], int] = {}
    for i in range(len(period_times)):
        on_this = [pp["player"] for pp in player_periods if pp["on"][i]]
        for a, b in combinations(sorted(on_this), 2):
            pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1
    co_play = [
        {"pair": f"{a} / {b}", "players": [a, b], "count": c}
        for (a, b), c in sorted(pair_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    # Preference labels
    pref_defs = {d.key: d.name for d in BOOLEAN_PREFERENCE_DEFINITIONS}
    prefs = [
        {"name": pref_defs.get(k, k), "enabled": v}
        for k, v in config.get("boolean_preferences", {}).items()
    ]

    return {
        "solved": True,
        "status": status,
        "players": players,
        "first_half": all_rows[: periods_per_half[0]],
        "second_half": all_rows[periods_per_half[0] :],
        "summary": summary,
        "co_play": co_play,
        "config": config,
        "prefs": prefs,
    }
