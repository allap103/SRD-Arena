"""Inspect one episode, turn and command without rendering every nested record."""

import json
from pathlib import Path
from typing import Any

import streamlit as st

from .command_outcomes import command_outcome
from .inspection_store import index, read_record, signature, summary_index, trace_events
from .inspector_widgets import paginated, selected_run


def episodes() -> None:
    """Select a completed or locally unfinished episode by number."""
    st.title("Episode details")
    run = selected_run()
    summaries = {
        record.episode: (revision, record) for revision, record in summary_index(run)
    }
    local_traces = {
        int(p.stem.split("-")[-1]): p
        for p in (run / "traces").glob("episode-*.jsonl")
        if p.stem.split("-")[-1].isdigit()
    }
    available = sorted(set(summaries) | set(local_traces))
    if not available:
        st.info("No summaries or traces yet. Record traces with --trace-every 1.")
        return
    episode = st.number_input(
        "Episode",
        min_value=min(available),
        max_value=max(available),
        value=max(available),
        key=f"episode_{run}",
    )
    if episode not in available:
        st.info("This episode is missing from the available history.")
        return
    path = local_traces.get(episode, run / "traces" / f"episode-{episode:06d}.jsonl")
    names: dict[str, str] = {}
    if episode in summaries:
        revision, record = summaries[episode]
        summary = read_record(revision, record)
        path = Path(revision[0]).parent / "traces" / f"episode-{episode:06d}.jsonl"
        names = {ref: c["name"] for ref, c in summary["creatures"].items()}
        st.caption(
            f"Episode {episode} · {summary.get('episode_outcome', 'completed')} · reward {summary.get('reward', 'unavailable')} · {path.parent.parent.name}"
        )
        if st.toggle("Show episode summary"):
            st.dataframe(
                [{"actor": ref, **v} for ref, v in summary["creatures"].items()],
                hide_index=True,
            )
            st.json(
                {
                    k: summary[k]
                    for k in (
                        "reward_components",
                        "fallen_party_members",
                        "event_counts",
                        "rejection_reasons",
                    )
                    if k in summary
                }
            )
            st.caption(
                "Damage totals use recorded events; persistent effects may lack attribution."
            )
    else:
        st.info(
            "Unfinished episode: no completed summary yet. The final recorded command may not finish its turn."
        )
    render_trace(path, names)


def render_trace(path: Path, names: dict[str, str]) -> None:
    """Seek to one command; defer snapshots, policy alternatives and event JSON."""
    revision = signature(path)
    records = index(revision)
    if not records:
        st.info(
            "No committed trace records for this episode. Use --trace-every 1 for every episode."
        )
        return
    actors = sorted({r.actor for r in records if r.actor is not None})
    selected = st.multiselect(
        "Combatants",
        actors,
        default=actors,
        format_func=lambda ref: f"{names.get(ref, ref)} [{ref}]",
    )
    turns = list(dict.fromkeys((r.round, r.turn_actor) for r in records))
    turn_labels = {f"Round {t[0]} — {t[1]}": t for t in turns}
    turn = turn_labels[st.selectbox("Turn", list(turn_labels))]
    shown = [
        r
        for r in records
        if (r.round, r.turn_actor) == turn
        and (r.actor in selected or r.controller == "initial")
    ]
    if not shown:
        st.info("No commands by the selected combatants in this turn.")
        return
    paginated(
        [{"sequence": r.sequence, "actor": r.actor, "command": r.label} for r in shown],
        key="commands",
    )
    commands = {f"#{r.sequence}": r for r in shown}
    record = commands[st.selectbox("Command", list(commands))]
    row = read_record(revision, record)
    outcome = (
        "initial state"
        if row["controller"] == "initial"
        else command_outcome(
            kind=row["kind"],
            selected_id=row["action_id"],
            rejection=row["rejection"],
            events=row["events"],
            resolution_events=trace_events(revision)
            if row["kind"] == "spell"
            else None,
        )
    )
    st.subheader(f"{row['label']} — {outcome}")
    st.write(
        {
            k: row[k]
            for k in (
                "controller",
                "decision_kind",
                "command_seconds",
                "action_id",
                "decision_id",
            )
        }
    )
    st.json(row["command"])
    if st.toggle("Show before / after"):
        left, right = st.columns(2)
        for container, phase in ((left, "before"), (right, "after")):
            container.dataframe(
                [{"actor": a, **v} for a, v in row[phase].items()], hide_index=True
            )
    if row.get("policy") and st.toggle("Show model decision"):
        policy = row["policy"]
        st.json({k: v for k, v in policy.items() if k != "top_choices"})
        st.dataframe(policy.get("top_choices", []), hide_index=True)
    if st.toggle("Show recorded events"):
        st.caption(
            "Events retain their own actor, action and frame IDs and may resolve earlier actions."
        )
        st.json(row["events"])
    identifier = st.text_input("Find exact action_id or frame_id")
    if identifier:
        matches: list[dict[str, Any]] = [
            e
            for e in trace_events(revision)
            if identifier in (e.get("action_id"), e.get("frame_id"))
        ]
        paginated(
            [{**e, "data": json.dumps(e.get("data", {}))} for e in matches],
            key="event_matches",
        )
