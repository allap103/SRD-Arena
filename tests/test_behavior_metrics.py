"""Offline comparison metrics preserve spell outcomes and trace denominators."""

import json
from pathlib import Path
from typing import Any

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import Session
from srd_arena.training.behavior_metrics import (
    instantaneous_damage_areas,
    report,
    trace_metrics,
)


def test_damage_area_classification_uses_mechanics_and_excludes_persistent_control() -> (
    None
):
    """The fixed warlock's instant damage areas qualify by mechanics, not name rules."""
    game = Session(
        EncounterCatalog().load_encounter("warlock_goblin_pressure"), seed=42
    )
    actor = next(
        c
        for c in game.observe_gameplay().creatures
        if c.combat.creature_ref == "warlock"
    )
    assert instantaneous_damage_areas(actor.spell_capabilities) == [
        "burning_hands",
        "fireball",
    ]


def command(
    kind: str, start: int, end: int, *, round_number: int = 1, rejected: bool = False
) -> dict[str, Any]:
    """Make the relevant subset of a recorded warlock command."""
    return {
        "actor": "warlock",
        "controller": "model",
        "kind": kind,
        "round": round_number,
        "turn_actor": "warlock",
        "rejection": "no" if rejected else None,
        "before": {"warlock": {"position": {"x": start, "y": 0}}},
        "after": {"warlock": {"position": {"x": end, "y": 0}}},
        "events": [],
    }


def test_resolved_empty_damage_cast_is_not_a_rejection_or_zero_damage_hit() -> None:
    events = [
        {
            "seq": 1,
            "actor": "warlock",
            "type": "spell_cast",
            "action_id": "empty",
            "data": {"spell_id": "fireball", "target_refs": []},
        },
        {
            "seq": 2,
            "actor": "warlock",
            "type": "spell_cast",
            "action_id": "saved",
            "data": {"spell_id": "fireball", "target_refs": ["goblin"], "damage": 0},
        },
        {
            "seq": 3,
            "actor": "warlock",
            "type": "spell_cast",
            "action_id": "cloud",
            "data": {"spell_id": "stinking_cloud", "target_refs": []},
        },
        {
            "seq": 4,
            "actor": "enemy",
            "type": "spell_cast",
            "action_id": "enemy",
            "data": {"spell_id": "fireball", "target_refs": []},
        },
        {
            "seq": 5,
            "actor": "warlock",
            "type": "spell_cast",
            "action_id": "unknown",
            "data": {"spell_id": "fireball"},
        },
    ]
    row = command("decline_d20_modifier", 0, 0)
    row["events"] = events  # Resolutions can arrive on a later interrupt command.
    result = trace_metrics(
        [command("spell", 0, 0, rejected=True), row, row], "warlock", {"fireball"}
    )
    assert result["instant_damage_area_casts"] == 3
    assert result["empty_damage_area_casts"] == 1


def test_reversals_require_actual_consecutive_movement_in_the_same_turn() -> None:
    rows = [
        command("move", 0, 1),
        command("move", 1, 0),
        command("spell", 0, 0),
        command("move", 0, 1),
        command("move", 1, 0, round_number=2),
        command("move", 0, 0),
        command("move", 0, 1, round_number=2),
    ]
    result = trace_metrics(rows, "warlock", set())
    assert result["moves"] == 5
    assert result["consecutive_move_pairs"] == result["immediate_reversals"] == 1


def test_report_separates_completed_episodes_from_sampled_traces(
    tmp_path: Path,
) -> None:
    def summary(ep: int, win: bool, slots: int) -> dict[str, Any]:
        return {
            "episode": ep,
            "reward": 1 if win else -1,
            "episode_outcome": "win" if win else "loss",
            "fallen_party_members": [] if win else ["warlock"],
            "creatures": {
                "warlock": {
                    "spell_slots_remaining": slots,
                    "recorded_spell_damage_to_allies": 5,
                }
            },
        }

    (tmp_path / "combat-summary.jsonl").write_text(
        "\n".join(json.dumps(summary(i, i == 1, i == 1)) for i in (1, 2)) + "\n"
    )
    (tmp_path / "traces").mkdir()
    (tmp_path / "traces/episode-000001.jsonl").write_text(
        json.dumps(command("move", 0, 1)) + "\n"
    )
    result = report(tmp_path, actor="warlock", damage_areas=set())["aggregate"]
    assert result["episodes"] == 2 and result["traced_episodes"] == 1
    assert result["win_rate"] == 0.5 and result["slot_preserving_win_rate"] == 1
    assert result["mean_moves_per_traced_episode"] == 1
    assert result["empty_damage_area_cast_rate"] is None
