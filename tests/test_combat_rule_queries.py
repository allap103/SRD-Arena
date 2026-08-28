from srd_arena.domain.creatures import Attributes, Creature, Equipment, Inventory
from srd_arena.domain.effects.modifiers import RollModifier
from srd_arena.domain.effects.results import EffectResult
from srd_arena.domain.effects.rule_effects import (
    ActionEconomyKind,
    ActionEconomyRestriction,
    ArmorClassAdjustment,
    AttackLimit,
    InvocationFailureChance,
    ReactionProhibition,
    RollAdjustment,
    RuntimeRuleEffect,
    SpeedAdjustment,
    SpeedMultiplier,
)
from srd_arena.domain.effects.runtime import (
    EffectSource,
    EffectSourceKind,
    OngoingEffect,
    OngoingEffectKind,
    RuntimeStateIdentity,
)
from srd_arena.domain.encounters.definitions import (
    EncounterBehavior,
    EncounterDefinition,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import (
    ActionCost,
    EncounterAction,
)
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.ongoing_effects import remove_ongoing_effects
from srd_arena.domain.encounters.rule_queries import (
    InvocationStartContext,
    action_compatibility,
    attack_limit,
    effective_armor_class,
    effective_speed,
    invocation_start_checks,
    movement_budget,
    reaction_eligibility,
    resolve_invocation_start,
    roll_modifiers,
)
from srd_arena.domain.geometry import (
    Grid,
    MovementBudget,
    MovementCost,
    Position,
)

ACTOR_REF = "participant:target"


def _encounter() -> EncounterState:
    creature = Creature(
        id="target",
        name="Target",
        description="",
        inventory=Inventory(),
        attributes=Attributes(
            base_health=10,
            level=1,
            strength=10,
            dexterity=10,
            constitution=10,
            wisdom=10,
            intelligence=10,
            charisma=10,
            base_armor_class=10,
        ),
        equipment=Equipment(),
    )
    participant = EncounterCreatureState(
        creature_id=creature.id,
        creature=creature,
        position=Position(1, 1),
        behavior=EncounterBehavior(type="wait"),
    )
    return EncounterState(
        encounter_id="rule-query-test",
        definition=EncounterDefinition(
            id="rule-query-test",
            grid=Grid(width=10, height=10),
        ),
        creatures={ACTOR_REF: participant},
        initiative_order=[ACTOR_REF],
    )


def _ongoing_effect(
    state_id: str,
    *rule_effects: RuntimeRuleEffect,
    definition_id: str = "test-effect",
) -> OngoingEffect:
    return OngoingEffect(
        identity=RuntimeStateIdentity(
            id=state_id,
            source=EffectSource(
                kind=EffectSourceKind.SPELL,
                definition_id=definition_id,
                applied_by_ref="participant:caster",
                origin_id=f"origin:{state_id}",
            ),
        ),
        target_refs=(ACTOR_REF,),
        kind=OngoingEffectKind.SPELL,
        rule_effects=rule_effects,
    )


def test_effective_armor_class_preserves_its_source() -> None:
    state = _encounter()
    shield = _ongoing_effect(
        "effect:shield-of-faith",
        ArmorClassAdjustment(2),
        definition_id="shield_of_faith",
    )
    state.ongoing_effects.append(shield)

    result = effective_armor_class(state, ACTOR_REF)

    assert result.base == 10
    assert result.value == 12
    assert tuple(
        contribution.provider_state_id for contribution in result.contributions
    ) == (shield.identity.id,)
    assert result.contributions[0].source == shield.identity.source


def test_speed_composes_addition_and_multiplication_into_movement_budget() -> None:
    state = _encounter()
    longstrider = _ongoing_effect(
        "effect:longstrider",
        SpeedAdjustment(10),
        definition_id="longstrider",
    )
    slow = _ongoing_effect(
        "effect:slow",
        SpeedMultiplier(1, 2),
        definition_id="slow",
    )
    state.ongoing_effects.extend((longstrider, slow))

    speed = effective_speed(state, ACTOR_REF)
    movement = movement_budget(state, ACTOR_REF)

    assert speed.base == 30
    assert speed.value == 20
    assert movement.speed == speed
    assert movement.budget == 4


def test_same_definition_rule_effects_do_not_stack_but_remain_independent() -> None:
    state = _encounter()
    first = _ongoing_effect(
        "effect:longstrider:first",
        SpeedAdjustment(10),
        definition_id="longstrider",
    )
    second = _ongoing_effect(
        "effect:longstrider:second",
        SpeedAdjustment(10),
        definition_id="longstrider",
    )
    state.ongoing_effects.extend((first, second))

    active = effective_speed(state, ACTOR_REF)

    assert active.value == 40
    assert tuple(
        contribution.provider_state_id for contribution in active.contributions
    ) == (first.identity.id,)

    state.ongoing_effects.remove(first)
    remaining = effective_speed(state, ACTOR_REF)

    assert remaining.value == 40
    assert tuple(
        contribution.provider_state_id for contribution in remaining.contributions
    ) == (second.identity.id,)


def test_effect_lifecycle_queries_speed_without_losing_movement_debt() -> None:
    state = _encounter()
    creature_state = state.creatures[ACTOR_REF]
    creature_state.movement_spent_this_turn = MovementCost(4)
    creature_state.movement_remaining = MovementBudget(2)
    applied = state._start_ongoing_effect(
        EffectResult(
            kind="start_ongoing_effect",
            target_ref=ACTOR_REF,
            data={
                "source_ref": "participant:caster",
                "source_label": "Slowing effect",
                "definition_id": "slowing_effect",
                "effect_kind": "spell",
            },
            rule_effects=(SpeedAdjustment(-20),),
        ),
        "origin:slowing-effect",
    )

    assert isinstance(applied.rule_effects[0], SpeedAdjustment)
    assert creature_state.creature.speed_modifier_sources == {}
    assert effective_speed(state, ACTOR_REF).value == 10
    assert creature_state.movement_remaining == 0

    remove_ongoing_effects(
        state,
        EffectResult(
            kind="remove_ongoing_effect",
            target_ref=ACTOR_REF,
            data={"effect_id": applied.identity.id},
        ),
    )

    assert effective_speed(state, ACTOR_REF).value == 30
    assert creature_state.movement_remaining == 2


def test_zero_speed_overrides_other_speed_contributions_and_movement() -> None:
    state = _encounter()
    state.ongoing_effects.extend(
        (
            _ongoing_effect(
                "effect:speed-bonus",
                SpeedAdjustment(10),
                definition_id="speed-bonus",
            ),
            _ongoing_effect(
                "effect:speed-halved",
                SpeedMultiplier(1, 2),
                definition_id="speed-halved",
            ),
            _ongoing_effect(
                "effect:speed-zero",
                SpeedMultiplier(0, 1),
                definition_id="speed-zero",
            ),
        )
    )

    assert effective_speed(state, ACTOR_REF).value == 0
    assert movement_budget(state, ACTOR_REF).budget == 0


def test_reaction_prohibition_reports_the_effect_state_id() -> None:
    state = _encounter()
    slow = _ongoing_effect(
        "effect:slow",
        ReactionProhibition(),
        definition_id="slow",
    )
    state.ongoing_effects.append(slow)

    eligibility = reaction_eligibility(
        state,
        ACTOR_REF,
        reaction_kind="opportunity_attack",
    )

    assert eligibility.allowed is False
    assert any(
        slow.identity.id in failure.state_ids for failure in eligibility.failures
    )


def test_action_and_bonus_action_become_incompatible_after_one_is_spent() -> None:
    state = _encounter()
    slow = _ongoing_effect(
        "effect:slow",
        ActionEconomyRestriction(
            frozenset(
                {
                    ActionEconomyKind.ACTION,
                    ActionEconomyKind.BONUS_ACTION,
                }
            )
        ),
        definition_id="slow",
    )
    state.ongoing_effects.append(slow)
    actor = state.creatures[ACTOR_REF]

    actor.bonus_action_available = False
    actor.bonus_action_used_this_turn = True
    action = EncounterAction(
        "Attack",
        "attack",
        creature_ref=ACTOR_REF,
        cost=ActionCost(action=1),
    )
    action_result = action_compatibility(state, ACTOR_REF, action)

    assert action_result.allowed is False
    assert any(
        slow.identity.id in failure.state_ids for failure in action_result.failures
    )

    actor.bonus_action_available = True
    actor.bonus_action_used_this_turn = False
    actor.actions_remaining = 0
    actor.action_used_this_turn = True
    bonus_action = EncounterAction(
        "Bonus action",
        "feature",
        creature_ref=ACTOR_REF,
        cost=ActionCost(bonus_action=1),
    )
    bonus_result = action_compatibility(state, ACTOR_REF, bonus_action)

    assert bonus_result.allowed is False
    assert any(
        slow.identity.id in failure.state_ids for failure in bonus_result.failures
    )

    actor.actions_remaining = 1
    regained_action_result = action_compatibility(
        state,
        ACTOR_REF,
        bonus_action,
    )

    assert regained_action_result.allowed is False
    assert any(
        slow.identity.id in failure.state_ids
        for failure in regained_action_result.failures
    )


def test_attack_limit_caps_the_base_number_and_preserves_its_source() -> None:
    state = _encounter()
    slow = _ongoing_effect(
        "effect:slow",
        AttackLimit(1),
        definition_id="slow",
    )
    state.ongoing_effects.append(slow)

    result = attack_limit(state, ACTOR_REF, base=3)

    assert result.value == 1
    assert tuple(
        contribution.provider_state_id for contribution in result.contributions
    ) == (slow.identity.id,)


def test_roll_query_composes_numeric_and_mode_adjustments() -> None:
    state = _encounter()
    slow = _ongoing_effect(
        "effect:slow",
        RollAdjustment(
            RollModifier(
                roll="saving_throw",
                mode="subtract",
                value=2,
                ability="dexterity",
            )
        ),
        RollAdjustment(
            RollModifier(
                roll="saving_throw",
                mode="disadvantage",
                ability="dexterity",
            )
        ),
        definition_id="slow",
    )
    state.ongoing_effects.append(slow)

    result = roll_modifiers(
        state,
        ACTOR_REF,
        "saving_throw",
        ability="dexterity",
    )

    assert result.resolve_modifier(lambda _sides: 1) == -2
    assert result.mode == "disadvantage"
    assert {
        contribution.provider_state_id for contribution in result.contributions
    } == {slow.identity.id}


def test_invocation_failure_is_component_gated_and_uses_injected_randomness() -> None:
    state = _encounter()
    slow = _ongoing_effect(
        "effect:slow",
        InvocationFailureChance(
            invocation_kinds=frozenset({"cast_spell"}),
            required_components=frozenset({"somatic"}),
            numerator=1,
            denominator=4,
            code="slow.somatic_spell_failure",
            message="The spell fails because its gestures are too slow.",
        ),
        definition_id="slow",
    )
    state.ongoing_effects.append(slow)

    checks = invocation_start_checks(
        state,
        InvocationStartContext(
            actor_ref=ACTOR_REF,
            kind="cast_spell",
            components=frozenset({"somatic", "verbal"}),
        ),
    )
    failed = resolve_invocation_start(checks, roller=lambda _sides: 1)

    assert failed.allowed is False
    assert failed.rolls[0].roll == 1
    assert failed.rolls[0].failed is True
    failure = failed.failures[0].contribution
    assert failure.provider_state_id == slow.identity.id
    assert failure.code == "slow.somatic_spell_failure"

    roller_called = False

    def unexpected_roll(_sides: int) -> int:
        nonlocal roller_called
        roller_called = True
        return 1

    non_somatic_checks = invocation_start_checks(
        state,
        InvocationStartContext(
            actor_ref=ACTOR_REF,
            kind="cast_spell",
            components=frozenset({"verbal"}),
        ),
    )
    allowed = resolve_invocation_start(non_somatic_checks, roller=unexpected_roll)

    assert allowed.allowed is True
    assert allowed.rolls == ()
    assert roller_called is False
