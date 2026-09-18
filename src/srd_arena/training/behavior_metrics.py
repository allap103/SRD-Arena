"""Read-only behavior measurements from completed episode summaries and traces."""

import argparse
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from statistics import mean
from typing import Any

from srd_arena.engine.api import SpellCapabilityObservation

from .inspection_data import read_jsonl


def _has_damage(value: object) -> bool:
    if isinstance(value, Mapping):
        return value.get("type") == "damage_effect" or any(
            _has_damage(v) for v in value.values()
        )
    return isinstance(value, (tuple, list)) and any(_has_damage(v) for v in value)


def instantaneous_damage_areas(
    catalog: Iterable[SpellCapabilityObservation],
) -> list[str]:
    """Select declarative instant damage areas; exclude persistent/control effects."""
    result = set()
    for spell in catalog:
        durations = spell.mechanics.get("durations", ())
        if (
            spell.target_kind == "area"
            and spell.mechanics.get("implementation") == "declarative"
            and isinstance(durations, (tuple, list))
            and durations
            and all(
                isinstance(d, Mapping) and d.get("kind") == "instant" for d in durations
            )
            and _has_damage(spell.mechanics.get("definition"))
        ):
            result.add(spell.spell_id)
    return sorted(result)


def trace_metrics(
    rows: Iterable[dict[str, Any]], actor: str, damage_areas: set[str]
) -> dict[str, int]:
    """Count resolved casts and actual consecutive reversals, never attempted effects.

    Empty means the resolved instantaneous damage area's target list is explicitly
    empty. A successful save, immunity, or zero damage to a target is not empty.
    Reversals are consecutive accepted voluntary movement commands by this actor
    in one turn, returning to the prior starting coordinate. This is a diagnostic
    proxy, not a claim that every return step is tactically wrong.
    """
    result = dict(
        instant_damage_area_casts=0,
        empty_damage_area_casts=0,
        moves=0,
        consecutive_move_pairs=0,
        immediate_reversals=0,
    )
    seen_events: set[int] = set()
    seen_casts: set[str] = set()
    last_move: tuple[tuple[object, object], object, object] | None = None
    for row in rows:
        for event in row.get("events", []):
            if event["seq"] in seen_events:
                continue
            seen_events.add(event["seq"])
            data = event.get("data", {})
            if (
                event.get("actor") != actor
                or event["type"] != "spell_cast"
                or data.get("spell_id") not in damage_areas
            ):
                continue
            key = str(event.get("action_id") or f"event:{event['seq']}")
            if key in seen_casts:
                continue
            seen_casts.add(key)
            result["instant_damage_area_casts"] += 1
            result["empty_damage_area_casts"] += data.get("target_refs") == []
        if row.get("actor") != actor or row.get("controller") == "initial":
            continue
        if row.get("rejection"):
            continue
        before = row.get("before", {}).get(actor, {}).get("position")
        after = row.get("after", {}).get(actor, {}).get("position")
        turn = (row.get("round"), row.get("turn_actor"))
        if (
            row.get("kind") != "move"
            or before is None
            or after is None
            or before == after
        ):
            last_move = None
            continue
        result["moves"] += 1
        if last_move is not None and turn == last_move[0] and before == last_move[2]:
            result["consecutive_move_pairs"] += 1
            result["immediate_reversals"] += after == last_move[1]
        last_move = (turn, before, after)
    return result


def report(run: Path, *, actor: str, damage_areas: set[str]) -> dict[str, Any]:
    """Aggregate completed episodes, keeping trace sampling denominators explicit."""
    summaries = read_jsonl(run / "combat-summary.jsonl")
    rows = []
    for summary in summaries:
        stats = summary["creatures"][actor]
        path = run / "traces" / f"episode-{summary['episode']:06d}.jsonl"
        row = {
            "episode": summary["episode"],
            "win": summary.get("episode_outcome") == "win",
            "reward": summary["reward"],
            "party_member_down": bool(summary.get("fallen_party_members")),
            "slots_remaining": stats["spell_slots_remaining"],
            "recorded_friendly_spell_damage": stats["recorded_spell_damage_to_allies"],
            "traced": path.exists(),
        }
        if path.exists():
            row.update(trace_metrics(read_jsonl(path), actor, damage_areas))
        rows.append(row)
    traced = [r for r in rows if r["traced"]]
    wins = [r for r in rows if r["win"]]
    aggregate: dict[str, Any] = {
        "schema": "behavior-comparison-v1",
        "actor": actor,
        "episodes": len(rows),
        "traced_episodes": len(traced),
        "instant_damage_area_spell_ids": sorted(damage_areas),
        "win_rate": mean(r["win"] for r in rows) if rows else None,
        "mean_reward": mean(r["reward"] for r in rows) if rows else None,
        "party_member_down_rate": mean(r["party_member_down"] for r in rows)
        if rows
        else None,
        "mean_slots_remaining": mean(r["slots_remaining"] for r in rows)
        if rows
        else None,
        "slot_preserving_win_rate": mean(r["slots_remaining"] > 0 for r in wins)
        if wins
        else None,
        "mean_recorded_friendly_spell_damage": mean(
            r["recorded_friendly_spell_damage"] for r in rows
        )
        if rows
        else None,
    }
    for key in (
        "instant_damage_area_casts",
        "empty_damage_area_casts",
        "moves",
        "consecutive_move_pairs",
        "immediate_reversals",
    ):
        aggregate[key] = sum(r[key] for r in traced)
        aggregate["mean_" + key + "_per_traced_episode"] = (
            mean(r[key] for r in traced) if traced else None
        )
    aggregate["empty_damage_area_cast_rate"] = (
        aggregate["empty_damage_area_casts"] / aggregate["instant_damage_area_casts"]
        if aggregate["instant_damage_area_casts"]
        else None
    )
    aggregate["immediate_reversal_rate"] = (
        aggregate["immediate_reversals"] / aggregate["consecutive_move_pairs"]
        if aggregate["consecutive_move_pairs"]
        else None
    )
    return {"aggregate": aggregate, "episodes": rows}


def main() -> None:
    """Analyze existing artifacts without opening or modifying a model checkpoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--actor", default="warlock")
    parser.add_argument(
        "--damage-area-spells",
        nargs="+",
        required=True,
        help="Spell IDs classified from the frozen experiment catalog",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            report(
                args.run_dir,
                actor=args.actor,
                damage_areas=set(args.damage_area_spells),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
