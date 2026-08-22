from tests.helpers import make_creature

from srd_arena.domain.capabilities.definitions import (
    AttackResolution,
    AutomaticResolution,
    CapabilityDefinition,
    DerivedDifficultyClass,
    FixedAttackBonus,
    Outcome,
    SavingThrowResolution,
)
from srd_arena.domain.capabilities.execution import (
    CapabilityExecutionContext,
    CapabilityExecutionStatistics,
    CapabilityTargetContext,
    resolve_capability,
)
from srd_arena.domain.capabilities.models import (
    CapabilityTarget,
    DamageEffect,
    OutcomeStage,
)


def test_non_spell_capability_executes_without_spell_domain_objects() -> None:
    actor = make_creature()
    target = make_creature()
    target.id = "target"
    target.name = "Target"
    starting_health = target.get_health()
    definition = CapabilityDefinition(
        target=CapabilityTarget(kind="creature"),
        resolution=AutomaticResolution(
            Outcome(effects=(DamageEffect("1d6", 0, "force"),))
        ),
    )

    result = resolve_capability(
        CapabilityExecutionContext(
            creature=actor,
            definition=definition,
            capability_id="force-pulse",
            capability_name="Force Pulse",
            statistics=CapabilityExecutionStatistics(
                save_dc=10,
                attack_bonus=0,
                ability_modifier=0,
            ),
            target=CapabilityTargetContext(
                creature=target,
                target_ref=target.id,
                target_label=target.name,
            ),
            current_round=1,
            roller=lambda _sides: 1,
        )
    )

    assert target.get_health() == starting_health - 1
    assert result.capability_id == "force-pulse"
    assert result.messages[0][1] == "Test Player uses Force Pulse on Target."
    assert result.details["base_resource_level"] == 0


def test_capability_uses_fixed_attack_bonus_instead_of_provider_statistics() -> None:
    actor = make_creature()
    target = make_creature()
    definition = CapabilityDefinition(
        target=CapabilityTarget(kind="creature"),
        resolution=AttackResolution(
            modes=("melee",),
            attack_bonus=FixedAttackBonus(7),
            hit=Outcome(effects=(DamageEffect("1d6", 0, "force"),)),
        ),
    )

    result = resolve_capability(
        CapabilityExecutionContext(
            creature=actor,
            definition=definition,
            capability_id="force-strike",
            capability_name="Force Strike",
            statistics=CapabilityExecutionStatistics(
                save_dc=10,
                attack_bonus=-100,
                ability_modifier=0,
            ),
            target=CapabilityTargetContext(
                creature=target,
                target_ref=target.id,
                target_label=target.name,
            ),
            current_round=1,
            roller=lambda _sides: 3,
        )
    )

    attack = result.details["attack_roll_detail"]
    assert isinstance(attack, dict)
    assert attack["modifier"] == 7
    assert attack["hit"] is True


def test_damage_uses_authored_bonus_ability_modifier_and_minimum() -> None:
    actor = make_creature()
    target = make_creature()
    starting_health = target.get_health()
    definition = CapabilityDefinition(
        target=CapabilityTarget(kind="creature"),
        resolution=AutomaticResolution(
            Outcome(
                effects=(
                    DamageEffect(
                        "1d6",
                        2,
                        "force",
                        minimum=8,
                        modifier="ability_modifier",
                    ),
                )
            )
        ),
    )

    resolve_capability(
        CapabilityExecutionContext(
            creature=actor,
            definition=definition,
            capability_id="force-pulse",
            capability_name="Force Pulse",
            statistics=CapabilityExecutionStatistics(10, 0, 3),
            target=CapabilityTargetContext(target, "target", "Target"),
            current_round=1,
            roller=lambda _sides: 1,
        )
    )

    assert target.get_health() == starting_health - 8


def test_resource_level_derived_save_dc_uses_the_selected_level() -> None:
    actor = make_creature()
    target = make_creature()
    definition = CapabilityDefinition(
        target=CapabilityTarget(kind="creature"),
        resolution=SavingThrowResolution(
            ability="dexterity",
            difficulty=DerivedDifficultyClass("ten_plus_resource_level"),
            failure=(OutcomeStage(effects=(DamageEffect("1d6", 0, "force"),)),),
        ),
    )

    result = resolve_capability(
        CapabilityExecutionContext(
            creature=actor,
            definition=definition,
            capability_id="level-save",
            capability_name="Level Save",
            statistics=CapabilityExecutionStatistics(99, 0, 0),
            target=CapabilityTargetContext(target, "target", "Target"),
            current_round=1,
            base_resource_level=1,
            resource_level=4,
            roller=lambda _sides: 1,
        )
    )

    save = result.details["save_detail"]
    assert isinstance(save, dict)
    assert save["target_dc"] == 14
