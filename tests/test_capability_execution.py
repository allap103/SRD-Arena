from tests.helpers import make_creature

from srd_arena.domain.capabilities.definitions import (
    AttackResolution,
    AutomaticResolution,
    CapabilityDefinition,
    FixedAttackBonus,
    Outcome,
)
from srd_arena.domain.capabilities.execution import (
    CapabilityExecutionContext,
    CapabilityExecutionStatistics,
    CapabilityTargetContext,
    resolve_capability,
)
from srd_arena.domain.capabilities.models import CapabilityTarget, DamageEffect


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
