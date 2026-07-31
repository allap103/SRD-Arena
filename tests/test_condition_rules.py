from srd_arena.domain.effects.condition_rules import effective_conditions
from srd_arena.domain.effects.conditions import (
    CombatTrait,
    Condition,
    build_applied_condition,
)


def _applied(condition: Condition, source_ref: str):
    return build_applied_condition(
        condition=condition,
        source_ref=source_ref,
        source_label=source_ref,
        target_ref="target",
    )


def test_paralyzed_exposes_incapacitated_without_an_applied_child() -> None:
    paralyzed = _applied(Condition.PARALYZED, "hold_person")

    effective = effective_conditions((paralyzed,))

    assert effective.has(Condition.PARALYZED)
    assert effective.has(Condition.INCAPACITATED)
    assert effective.has_trait(CombatTrait.CANNOT_TAKE_ACTIONS)
    assert effective.providers_for(Condition.INCAPACITATED) == (
        paralyzed.id,
    )


def test_effective_condition_preserves_all_independent_providers() -> None:
    paralyzed = _applied(Condition.PARALYZED, "hold_person")
    stunned = _applied(Condition.STUNNED, "mind_blast")

    effective = effective_conditions((paralyzed, stunned))

    assert effective.providers_for(Condition.INCAPACITATED) == tuple(
        sorted((paralyzed.id, stunned.id))
    )
    assert effective.providers_for_trait(
        CombatTrait.CANNOT_TAKE_REACTIONS
    ) == tuple(sorted((paralyzed.id, stunned.id)))


def test_immunity_suppresses_only_the_implied_condition() -> None:
    unconscious = _applied(Condition.UNCONSCIOUS, "sleep")

    effective = effective_conditions(
        (unconscious,),
        frozenset({Condition.PRONE}),
    )

    assert effective.has(Condition.UNCONSCIOUS)
    assert effective.has(Condition.INCAPACITATED)
    assert effective.has(Condition.PRONE) is False
    assert len(effective.suppressed_conditions) == 1
    suppressed = effective.suppressed_conditions[0]
    assert suppressed.condition is Condition.PRONE
    assert suppressed.provider_ids == (unconscious.id,)
    assert suppressed.reason == "immunity"
