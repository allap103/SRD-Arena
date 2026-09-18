"""Independent overview pages; combat logs are loaded only where requested."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import streamlit as st

from .inspection_data import action_totals
from .inspection_store import (
    Signature,
    document,
    index,
    lineage,
    metric_history,
    signature,
)
from .inspector_widgets import chart, paginated, selected_run


def learning() -> None:
    """Render one chart group without loading summaries, traces or raw tables."""
    st.title("Learning curves")
    rows = metric_history(selected_run())
    if not rows:
        st.info("No completed episode metrics yet.")
        return
    st.caption(
        f"{len(rows):,} completed episodes across available run history. Charts show at most 1,000 evenly sampled points after smoothing; use Episode table for exact values and short-lived spikes."
    )
    window = st.select_slider(
        "Trailing average (episodes)", options=[1, 5, 10, 20, 50, 100], value=20
    )
    group = st.radio(
        "Charts",
        ["Outcomes and rewards", "Loss and exploration", "Performance"],
        horizontal=True,
    )
    if group == "Outcomes and rewards":
        chart(
            [
                {
                    **r,
                    "win": int(r["episode_outcome"] == "win")
                    if "episode_outcome" in r
                    else int(r.get("reward", 0) > 0),
                }
                for r in rows
            ],
            ["reward", "win", "truncated"],
            window,
        )
        components = [
            {"episode": r["episode"], **r["reward_components"]}
            for r in rows
            if r.get("reward_components")
        ]
        if components:
            chart(
                components,
                sorted({k for r in components for k in r if k != "episode"}),
                window,
            )
    elif group == "Loss and exploration":
        st.caption(
            "Policy loss is not an accuracy score. Value loss includes its 0.5 coefficient."
        )
        chart(rows, ["policy_loss", "value_loss", "loss"], window)
        chart(rows, ["entropy", "gradient_norm"], window)
    else:
        chart(
            rows,
            [
                "inference_seconds",
                "environment_seconds",
                "update_seconds",
                "episode_seconds",
            ],
            window,
        )
        chart(rows, ["rejected_commands", "decisions", "engine_steps"], window)


def episode_table() -> None:
    """Paginate scalar metrics and reveal nested metadata only on demand."""
    st.title("Episode table")
    rows = metric_history(selected_run())
    if not rows:
        st.info("No completed episode metrics yet.")
        return
    outcome = st.selectbox("Outcome", ["All", "win", "loss", "draw", "truncated"])
    filtered = [
        r
        for r in rows
        if outcome == "All"
        or r.get(
            "episode_outcome",
            "win"
            if r.get("reward", 0) > 0
            else "loss"
            if r.get("reward", 0) < 0
            else "truncated"
            if r.get("truncated")
            else "draw",
        )
        == outcome
    ]
    columns = sorted(
        {
            k
            for r in rows
            for k, v in r.items()
            if isinstance(v, (int, float, str, bool)) or v is None
        }
    )
    defaults = [
        k
        for k in [
            "episode",
            "episode_outcome",
            "reward",
            "loss",
            "episode_seconds",
            "decisions",
            "rejected_commands",
        ]
        if k in columns
    ]
    chosen = st.multiselect("Columns", columns, default=defaults)
    paginated(
        [{k: r.get(k) for k in chosen} for r in reversed(filtered)], key="metrics"
    )


@lru_cache(maxsize=8)
def combat_aggregate(
    sources: tuple[tuple[Signature, int | None], ...], first: int, last: int
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Aggregate one selected range without keeping full episode summaries."""
    names: dict[str, str] = {}
    totals: dict[tuple[str, str, str], int] = {}
    for revision, limit in sources:
        if not revision[2]:
            continue
        with Path(revision[0]).open("rb") as stream:
            for item in index(revision):
                if not first <= item.episode <= last or (
                    limit is not None and item.episode > limit
                ):
                    continue
                stream.seek(item.offset)
                row = json.loads(stream.read(item.length))
                names.update({ref: c["name"] for ref, c in row["creatures"].items()})
                for action in action_totals([row], list(row["creatures"])):
                    key = action["actor"], action["action"], action["result"]
                    totals[key] = totals.get(key, 0) + action["count"]
    return names, [
        {"actor": a, "action": b, "result": c, "count": n}
        for (a, b, c), n in sorted(totals.items())
    ]


def combat() -> None:
    """Inspect bounded action totals independently of charts and turn details."""
    st.title("Combat totals")
    sources = lineage(selected_run(), "combat-summary.jsonl")
    episodes = [
        r.episode
        for revision, limit in sources
        for r in index(revision)
        if limit is None or r.episode <= limit
    ]
    if not episodes:
        st.info("No combat summaries yet.")
        return
    lo, hi = min(episodes), max(episodes)
    interval = (
        st.slider("Episode range", lo, hi, (max(lo, hi - 99), hi))
        if lo < hi
        else (lo, hi)
    )
    names, totals = combat_aggregate(sources, *interval)
    actors = st.multiselect(
        "Combatants",
        sorted(names),
        default=sorted(names),
        format_func=lambda ref: f"{names[ref]} [{ref}]",
    )
    st.caption(
        "Command attempts, not completed casts. Defaults to the latest 100 episodes; select a wider range to aggregate more."
    )
    paginated([r for r in totals if r["actor"] in actors], key="combat")


def comparisons() -> None:
    """Read evaluation comparison reports only on this page."""
    st.title("Evaluation comparisons")
    root = Path(st.session_state["inspector_root"])
    files = sorted(root.rglob("comparison.json"))
    if not files:
        st.info("No comparison reports found.")
        return
    selected = st.selectbox(
        "Comparison", files, format_func=lambda p: str(p.relative_to(root))
    )
    report = document(signature(selected))
    paginated(
        [
            {k: v for k, v in r.items() if not isinstance(v, (dict, list))}
            for r in report["controllers"]
        ],
        key="comparisons",
    )
    if st.toggle("Show creature means"):
        st.json({r["mode"]: r.get("creature_means", {}) for r in report["controllers"]})


def configuration() -> None:
    """Show saved configuration without imposing JSON rendering on other pages."""
    st.title("Configuration and provenance")
    for name in ("config.json", "manifest.json"):
        st.subheader(name)
        st.json(document(signature(selected_run() / name)))
    st.caption(
        "Available ancestor episodes before each resume boundary are included. Missing parent directories leave gaps in history."
    )
