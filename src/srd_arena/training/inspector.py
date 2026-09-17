"""Local Streamlit viewer for training curves, combat aggregates and turn traces."""

import argparse
import json
from pathlib import Path
from typing import Any

import streamlit as st

from srd_arena.training.command_outcomes import command_outcome
from srd_arena.training.inspection_data import action_totals, history, read_jsonl


def chart(rows: list[dict[str, Any]], fields: list[str], window: int) -> None:
    """Display episode-indexed metrics with optional trailing means."""
    available = [
        f for f in fields if any(isinstance(r.get(f), (float, int)) for r in rows)
    ]
    if not available:
        return
    data: dict[str, list[Any]] = {"episode": [r["episode"] for r in rows]}
    for field in available:
        series = [r.get(field) for r in rows]
        smoothed = []
        for i in range(len(series)):
            values = [
                v
                for v in series[max(0, i - window + 1) : i + 1]
                if isinstance(v, (float, int))
            ]
            smoothed.append(sum(values) / len(values) if values else None)
        data[field] = smoothed
    st.line_chart(data, x="episode", y=available)


def render(run: Path) -> None:
    """Inspect one run and the ancestor episodes preceding its resume boundary."""
    metrics = history(run, "metrics.jsonl")
    summaries = history(run, "combat-summary.jsonl")
    st.caption(
        "Privileged spectator diagnostics. Accepted commands can still miss or have no effect."
    )
    with st.expander("Configuration and provenance"):
        for name in ("config.json", "manifest.json"):
            if (run / name).exists():
                st.write(name)
                st.json(json.loads((run / name).read_text()))
        st.caption(
            "Ancestor logs are read where available. Moving or deleting a parent can leave gaps in the history."
        )
    window = st.select_slider(
        "Trailing average (episodes)", options=[1, 5, 10, 20, 50], value=1
    )
    if metrics:
        st.subheader("Learning and outcomes")
        st.caption(
            "Policy loss is not an accuracy score. Value loss includes its 0.5 coefficient. Training and evaluation are separate reports."
        )
        chart(metrics, ["policy_loss", "value_loss", "loss"], window)
        chart(metrics, ["entropy", "gradient_norm"], window)
        chart(
            [{**r, "win": int(r.get("reward", 0) > 0)} for r in metrics],
            ["reward", "win", "truncated"],
            window,
        )
        with st.expander("Timing and rejection trends"):
            chart(
                metrics,
                ["inference_seconds", "environment_seconds", "update_seconds"],
                window,
            )
            chart(metrics, ["rejected_commands", "decisions", "engine_steps"], window)
        st.dataframe(metrics, hide_index=True)
    completed_local = {
        r["episode"] for r in summaries if Path(r["source_run"]) == run.resolve()
    }
    incomplete = [
        p
        for p in sorted((run / "traces").glob("episode-*.jsonl"))
        if int(p.stem.split("-")[-1]) not in completed_local
    ]
    if incomplete and (not summaries or st.toggle("Inspect unfinished episodes")):
        name = st.selectbox("Unfinished trace", [p.name for p in incomplete])
        path = run / "traces" / name
        rows = read_jsonl(path)
        st.info(
            "This trace has no completed episode summary. Its last command is not necessarily a completed turn."
        )
        render_trace(path, list(rows[0]["before"]) if rows else [])
        return
    if not summaries:
        st.info("No combat summaries yet. Older runs may have only training metrics.")
        return
    lo, hi = min(r["episode"] for r in summaries), max(r["episode"] for r in summaries)
    interval = (
        st.slider("Episode range for action totals", lo, hi, (lo, hi))
        if lo < hi
        else (lo, hi)
    )
    selected = [r for r in summaries if interval[0] <= r["episode"] <= interval[1]]
    names = {
        ref: info["name"] for s in selected for ref, info in s["creatures"].items()
    }
    actors = st.multiselect(
        "Combatants",
        sorted(names),
        default=sorted(names),
        format_func=lambda ref: f"{names[ref]} [{ref}]",
    )
    st.subheader("Command usage")
    st.caption(
        "Attempts grouped by action identity; aiming coordinates remain in the trace. Multi-stage commands are not separate spell casts."
    )
    st.dataframe(action_totals(selected, actors), hide_index=True)
    episode = st.selectbox("Inspect episode", [r["episode"] for r in summaries])
    summary = next(r for r in summaries if r["episode"] == episode)
    st.subheader("Creature contributions and resources")
    st.dataframe(
        [
            {"actor": ref, **values}
            for ref, values in summary["creatures"].items()
            if ref in actors
        ],
        hide_index=True,
    )
    st.caption(
        "Attack and spell damage are separate recorded-event totals. Spell damage uses applied_damage per target; persistent effects and missing event details may be absent."
    )
    with st.expander("Episode event totals and rejection reasons"):
        st.json({k: summary[k] for k in ("event_counts", "rejection_reasons")})
    trace_path = Path(summary["source_run"]) / "traces" / f"episode-{episode:06d}.jsonl"
    render_trace(trace_path, actors)


def render_trace(path: Path, actors: list[str]) -> None:
    """Display turns, decisions and exact engine attribution identifiers."""
    rows = read_jsonl(path)
    if not rows:
        st.info(
            "No detailed trace for this episode. Use --trace-every 1 to record every episode."
        )
        return
    turns = list(dict.fromkeys((r["round"], r["turn_actor"] or "setup") for r in rows))
    turn_labels = {f"Round {t[0]} — {t[1]}": t for t in turns}
    turn = turn_labels[st.selectbox("Turn", list(turn_labels))]
    shown = [
        r
        for r in rows
        if (r["round"], r["turn_actor"] or "setup") == turn
        and (r["actor"] in actors or r["controller"] == "initial")
    ]
    if not shown:
        st.info("No commands by the selected combatants in this turn.")
    resolution_events = [e for row in rows for e in row["events"]]
    for row in shown:
        result = (
            "initial state"
            if row["controller"] == "initial"
            else command_outcome(
                kind=row["kind"],
                selected_id=row["action_id"],
                rejection=row["rejection"],
                events=row["events"],
                resolution_events=resolution_events,
            )
        )
        with st.expander(
            f"#{row['sequence']} {row['actor']} — {row['label']} — {result}"
        ):
            st.write(
                {
                    "controller": row["controller"],
                    "decision": row["decision_kind"],
                    "command_seconds": row["command_seconds"],
                }
            )
            if row["policy"]:
                policy = row["policy"]
                st.write(
                    {
                        k: v
                        for k, v in policy.items()
                        if k not in {"top_choices", "selected"}
                    }
                )
                st.write("Selected command")
                st.json(policy["selected"])
                st.write(
                    "Top alternatives (the selected command may be outside this list)"
                )
                st.dataframe(policy.get("top_choices", []), hide_index=True)
            else:
                st.json(row["command"])
            st.write("Before / after")
            left, right = st.columns(2)
            left.dataframe(
                [{"actor": a, **v} for a, v in row["before"].items()], hide_index=True
            )
            right.dataframe(
                [{"actor": a, **v} for a, v in row["after"].items()], hide_index=True
            )
            st.write("Recorded engine events")
            st.caption(
                "Events retain their own actor, action ID and frame ID. They may resolve an earlier action or a reaction; position in this list is not causal attribution."
            )
            st.json(row["events"])
            st.write({"action_id": row["action_id"], "decision_id": row["decision_id"]})
    with st.expander("Find events by engine action or frame ID"):
        identifier = st.text_input("Exact action_id or frame_id")
        if identifier:
            matches = [
                {
                    **e,
                    "boundary_sequence": r["sequence"],
                    "round": r["round"],
                    "turn_actor": r["turn_actor"],
                }
                for r in rows
                for e in r["events"]
                if identifier in (e["action_id"], e["frame_id"])
            ]
            st.json(matches)
            st.caption(
                "Matching identifiers only. Repeated action IDs do not establish a unique invocation."
            )


def main() -> None:
    """Serve local saved and live reports; refresh reloads available records."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    args, _ = parser.parse_known_args()
    st.set_page_config(page_title="Arena training inspector", layout="wide")
    st.title("Arena training inspector")
    st.button("Refresh records")
    runs = (
        sorted({p.parent for p in args.runs_dir.rglob("metrics.jsonl")})
        if args.runs_dir.exists()
        else []
    )
    if not runs:
        st.info(
            "No training records found. Start training with --trace-every 1 to capture turn details."
        )
        return
    comparisons = sorted(args.runs_dir.rglob("comparison.json"))
    if comparisons:
        with st.expander("Evaluation comparisons"):
            names = {str(p.relative_to(args.runs_dir)): p for p in comparisons}
            selected_report = names[st.selectbox("Comparison", list(names))]
            report = json.loads(selected_report.read_text())
            st.dataframe(
                [
                    {k: v for k, v in r.items() if k != "creature_means"}
                    for r in report["controllers"]
                ],
                hide_index=True,
            )
    run_labels = {str(p.relative_to(args.runs_dir)): p for p in runs}
    run = run_labels[st.selectbox("Run", list(run_labels))]
    try:
        render(run)
    except (ValueError, OSError, KeyError) as exc:
        st.error(f"Cannot read this report: {exc}")


if __name__ == "__main__":
    main()
