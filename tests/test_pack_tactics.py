"""Verify Pack Tactics from authored trait tag through shared roll queries."""

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.creatures import Creature
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.effects.rule_effects import AdjacentAllyAttackAdvantage
from srd_arena.domain.effects.runtime import EffectSourceKind
from srd_arena.domain.encounters.condition_state import apply_condition
from srd_arena.domain.encounters.definitions import (
    EncounterBehavior,
    EncounterDefinition,
    EncounterTeam,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.rule_queries import roll_modifiers
from srd_arena.domain.encounters.state_combat import attack_roll_mode_for
from srd_arena.domain.geometry import Grid, Position

BESTIARY = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)


def _monster(creature_id: str, name: str) -> Creature:
    return build_creature(
        CreatureSchema.model_validate(
            {
                "id": creature_id,
                "stat_block": {"name": name, "source": "XMM"},
            }
        ),
        bestiary=BESTIARY,
    )


def _encounter() -> EncounterState:
    wolf = _monster("wolf", "Wolf")
    ally = _monster("ally", "Wolf")
    target = _monster("target", "Goblin Warrior")
    behavior = EncounterBehavior(type="wait")
    creatures = {
        "wolf": EncounterCreatureState(
            "wolf",
            wolf,
            Position(1, 1),
            behavior,
        ),
        "ally": EncounterCreatureState(
            "ally",
            ally,
            Position(2, 2),
            behavior,
        ),
        "target": EncounterCreatureState(
            "target",
            target,
            Position(2, 1),
            behavior,
        ),
    }
    return EncounterState(
        "pack-tactics-test",
        EncounterDefinition(
            "pack-tactics-test",
            Grid(8, 8),
            teams=[
                EncounterTeam("pack", "Pack", ["wolf", "ally"], "scripted"),
                EncounterTeam("targets", "Targets", ["target"], "external"),
            ],
        ),
        creatures,
        initiative_order=["wolf", "ally", "target"],
    )


def test_pack_tactics_tag_builds_an_intrinsic_creature_rule() -> None:
    wolf = _monster("wolf", "Wolf")

    provider = wolf.combat_profile.intrinsic_rule_providers["pack_tactics"]

    assert provider.label == "Pack Tactics"
    assert provider.source_kind is EffectSourceKind.CREATURE
    assert provider.rule_effects == (AdjacentAllyAttackAdvantage(5),)


def test_pack_tactics_grants_sourced_advantage_with_an_eligible_ally() -> None:
    state = _encounter()

    result = roll_modifiers(
        state,
        "wolf",
        "attack_roll",
        opposing_ref="target",
    )

    assert result.mode == "advantage"
    assert len(result.contributions) == 1
    contribution = result.contributions[0]
    assert contribution.provider_state_id == "intrinsic:wolf:pack_tactics"
    assert contribution.source.kind is EffectSourceKind.CREATURE
    assert contribution.source.definition_id == "pack_tactics"
    assert (
        attack_roll_mode_for(
            state,
            "wolf",
            "target",
            "melee",
            state.creatures["wolf"].position,
            (),
        )
        == "advantage"
    )


def test_pack_tactics_requires_the_ally_to_be_near_the_target() -> None:
    state = _encounter()
    state.creatures["ally"].position = Position(6, 6)

    result = roll_modifiers(
        state,
        "wolf",
        "attack_roll",
        opposing_ref="target",
    )

    assert result.mode == "normal"


def test_incapacitated_ally_does_not_enable_pack_tactics() -> None:
    state = _encounter()
    apply_condition(
        state,
        build_applied_condition(
            condition=Condition.PARALYZED,
            source_ref="target",
            source_label="Target",
            target_ref="ally",
        ),
    )

    result = roll_modifiers(
        state,
        "wolf",
        "attack_roll",
        opposing_ref="target",
    )

    assert result.mode == "normal"
