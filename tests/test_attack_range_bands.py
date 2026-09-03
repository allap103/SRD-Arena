from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from srd_arena.domain.capabilities import CapabilityTarget, DamageEffect
from srd_arena.domain.creatures import AttackActionDefinition, Creature
from srd_arena.domain.encounters.actions.attack_resolution import (
    AttackRangeBand,
    attack_range_band_squares,
)
from srd_arena.domain.encounters.actions.eligibility_rules.attacks import AttackRule
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.terrain import CoverDegree, TerrainCell
from srd_arena.domain.geometry import Grid, GridDistance, Position


def _javelin_attacker() -> Creature:
    attack = AttackActionDefinition(
        name="Javelin",
        attack_modes=("melee", "ranged"),
        attack_bonus=6,
        target=CapabilityTarget("creature", range_feet=30),
        reach_feet=5,
        range_normal_feet=30,
        range_long_feet=120,
        hit=(DamageEffect("2d6", 4, "piercing"),),
    )
    return cast(
        Creature,
        SimpleNamespace(
            equipment=SimpleNamespace(right_hand=None, left_hand=None),
            stat_block_actions={"Javelin": attack},
            size="L",
        ),
    )


def test_mixed_attack_has_distinct_melee_and_ranged_bands() -> None:
    attacker = _javelin_attacker()
    grid = Grid(30, 30)

    melee = attack_range_band_squares(
        attacker,
        {},
        grid,
        preferred_attack_type="melee",
        preferred_attack_name="Javelin",
    )
    ranged = attack_range_band_squares(
        attacker,
        {},
        grid,
        preferred_attack_type="ranged",
        preferred_attack_name="Javelin",
    )

    assert melee == AttackRangeBand(GridDistance(1), GridDistance(1))
    assert ranged == AttackRangeBand(GridDistance(6), GridDistance(24))


def test_long_range_is_legal_but_imposes_disadvantage() -> None:
    band = AttackRangeBand(GridDistance(6), GridDistance(24))

    assert band.contains(GridDistance(24))
    assert band.roll_mode(GridDistance(6)) == "normal"
    assert band.roll_mode(GridDistance(7)) == "disadvantage"
    assert not band.contains(GridDistance(25))


def test_attack_eligibility_uses_the_maximum_range() -> None:
    actor_creature = _javelin_attacker()
    actor = SimpleNamespace(
        creature=actor_creature,
        actions_remaining=1,
        attacks_remaining=0,
        pending_multiattack=[],
    )
    target = SimpleNamespace(
        creature=SimpleNamespace(size="M"),
        position=Position(12, 0),
    )
    state = cast(
        EncounterState,
        SimpleNamespace(
            creatures={
                "ogre": SimpleNamespace(**vars(actor), position=Position(0, 0)),
                "target": target,
            },
            item_templates={},
            definition=SimpleNamespace(grid=Grid(30, 30), terrain=()),
        ),
    )
    action = EncounterAction(
        "Javelin",
        "attack",
        "target",
        preferred_attack_name="Javelin",
        preferred_attack_type="ranged",
    )

    with (
        patch(
            "srd_arena.domain.encounters.actions.eligibility_rules.attacks."
            "opposing_target_failure",
            return_value=None,
        ),
        patch(
            "srd_arena.domain.encounters.actions.eligibility_rules.attacks."
            "target_eligibility",
            return_value=SimpleNamespace(allowed=True, failures=()),
        ),
    ):
        failure = AttackRule().check(state, "ogre", action)

    assert failure is None


def test_attack_eligibility_rejects_a_target_behind_total_cover() -> None:
    actor_creature = _javelin_attacker()
    actor = SimpleNamespace(
        creature=actor_creature,
        actions_remaining=1,
        attacks_remaining=0,
        pending_multiattack=[],
    )
    state = cast(
        EncounterState,
        SimpleNamespace(
            creatures={
                "ogre": SimpleNamespace(**vars(actor), position=Position(0, 0)),
                "target": SimpleNamespace(
                    creature=SimpleNamespace(size="M"),
                    position=Position(12, 0),
                ),
            },
            item_templates={},
            definition=SimpleNamespace(
                grid=Grid(30, 30),
                terrain=(
                    TerrainCell(Position(6, 0), cover=CoverDegree.TOTAL),
                    TerrainCell(Position(6, 1), cover=CoverDegree.TOTAL),
                ),
            ),
        ),
    )
    action = EncounterAction(
        "Javelin",
        "attack",
        "target",
        preferred_attack_name="Javelin",
        preferred_attack_type="ranged",
    )

    with (
        patch(
            "srd_arena.domain.encounters.actions.eligibility_rules.attacks."
            "opposing_target_failure",
            return_value=None,
        ),
        patch(
            "srd_arena.domain.encounters.actions.eligibility_rules.attacks."
            "target_eligibility",
            return_value=SimpleNamespace(allowed=True, failures=()),
        ),
    ):
        failure = AttackRule().check(state, "ogre", action)

    assert failure is not None
    assert failure.code == "target_has_total_cover"
