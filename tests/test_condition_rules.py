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
    assert effective.has_trait(CombatTrait.INITIATIVE_DISADVANTAGE)
    assert effective.providers_for(Condition.INCAPACITATED) == (
        paralyzed.id,
    )


def test_paralyzed_and_unconscious_share_close_combat_traits() -> None:
    for condition in (Condition.PARALYZED, Condition.UNCONSCIOUS):
        applied = _applied(condition, "effect")
        effective = effective_conditions((applied,))

        for trait in (
            CombatTrait.ATTACKERS_HAVE_ADVANTAGE,
            CombatTrait.AUTO_FAIL_STRENGTH_SAVES,
            CombatTrait.AUTO_FAIL_DEXTERITY_SAVES,
            CombatTrait.HITS_WITHIN_5_FEET_ARE_CRITICAL,
        ):
            assert effective.providers_for_trait(trait) == (applied.id,)


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
    paralyzed = _applied(Condition.PARALYZED, "hold_person")

    effective = effective_conditions(
        (paralyzed,),
        frozenset({Condition.INCAPACITATED}),
    )

    assert effective.has(Condition.PARALYZED)
    assert effective.has(Condition.INCAPACITATED) is False
    assert len(effective.suppressed_conditions) == 1
    suppressed = effective.suppressed_conditions[0]
    assert suppressed.condition is Condition.INCAPACITATED
    assert suppressed.provider_ids == (paralyzed.id,)
    assert suppressed.reason == "immunity"
