"""The fixed training scenario needs help from the warlock to beat its archers."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from srd_arena.training.baselines import idle_action
from srd_arena.training.config import load_training_config


@pytest.mark.parametrize("participates", [False, True])
def test_goblin_pressure_separates_idle_and_blasting_warlock(
    participates: bool,
) -> None:
    config = load_training_config(Path("config/training/goblin_pressure.yaml"))
    environment = config.environment()
    transition = environment.reset(seed=config.encounter_seed)
    while not (transition.terminated or transition.truncated):
        choices = environment.choices
        if not participates:
            index = idle_action(choices)
        else:
            # This reference controller uses player-visible spell descriptors
            # omitted by the experimental numeric encoder. It establishes
            # solvability, not a learned-policy score or a training input.
            player = environment._adapter.observe_player("heroes")
            actions = {action.id: action for action in player.action_details}
            enemies = {
                row.creature_ref
                for row in player.creatures
                if row.allegiance == "enemy"
            }
            ranks = []
            for i, choice in enumerate(choices):
                action = actions.get(getattr(choice.command, "action_id", ""))
                score = 0
                if action is not None and action.source_id == "eldritch_blast":
                    score = 100
                elif choice.kind == "confirm_spell_targets":
                    score = 95
                elif (
                    choice.kind == "toggle_spell_target"
                    and choice.target_ref in enemies
                    and not choice.remove
                ):
                    score = 90
                elif (
                    choice.kind.startswith("decline_")
                    or choice.kind == "keep_initiative"
                ):
                    score = 2
                elif choice.kind == "wait":
                    score = 1
                ranks.append((score, -i, i))
            index = max(ranks)[2]
        prepared = environment.prepare_action(index, lambda encoded, choices: 0)
        transition = environment.step(
            prepared, expected_decision_id=transition.decision_id
        )
    assert transition.terminated and not transition.truncated
    assert transition.info["episode_outcome"] == ("win" if participates else "loss")
    components = transition.info["reward_components"]
    assert isinstance(components, dict)
    assert components["outcome"] == (1.0 if participates else -1.0)
    assert transition.reward == pytest.approx(sum(components.values()))
    if not participates:
        assert transition.info["fallen_party_members"] == ["barbarian", "warlock"]
        assert components["party_member_down"] == -0.8
    casts = [
        event
        for event in environment.spectator_snapshot().history
        if event.type == "spell_cast" and event.creature_ref == "warlock"
    ]
    if participates:
        assert casts
        goblin_damage = 0
        for event in environment.spectator_snapshot().history:
            if (
                event.type != "spell_projectile_resolved"
                or event.creature_ref != "warlock"
            ):
                continue
            details = event.data.get("damage_roll_details", ())
            assert isinstance(details, (list, tuple))
            for detail in details:
                if isinstance(detail, Mapping) and str(
                    detail.get("target_ref", "")
                ).startswith("goblin_"):
                    goblin_damage += int(str(detail.get("applied_damage", 0)))
        assert goblin_damage > 0
    else:
        assert not casts
        reset = environment.reset(seed=config.encounter_seed)
        assert reset.info["fallen_party_members"] == []
