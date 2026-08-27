"""Encounter queries for Armor Class, Speed, and attack limits."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...effects.condition_rules import effective_conditions
from ...effects.conditions import CombatTrait
from ...effects.rule_effects import (
    ArmorClassAdjustment,
    AttackLimit,
    SpeedAdjustment,
    SpeedMultiplier,
)
from ..models import CreatureRef
from .models import (
    MovementQueryResult,
    NumericOperation,
    NumericRuleContribution,
    NumericRuleResult,
)
from .providers import legacy_modifier_provider, ongoing_rule_effects

if TYPE_CHECKING:
    from ..encounter import EncounterState


def effective_armor_class(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> NumericRuleResult:
    """Return effective AC with every modifier's runtime provenance.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     attributes=SimpleNamespace(base_armor_class=10, dexterity=14),
    ...     get_modifier=lambda score: (score - 10) // 2,
    ...     armor_class_modifier_sources={},
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(creature=creature)},
    ...     ongoing_effects=[],
    ... )
    >>> effective_armor_class(state, "hero").value
    12
    """

    creature = state.creatures[creature_ref].creature
    base = creature.attributes.base_armor_class + creature.get_modifier(
        creature.attributes.dexterity
    )
    contributions: list[NumericRuleContribution] = []
    for definition_id, sources in creature.armor_class_modifier_sources.items():
        if not sources:
            continue
        origin_id, value = max(
            sources.items(),
            key=lambda item: (item[1], item[0]),
        )
        provider_state_id, source = legacy_modifier_provider(
            state,
            creature_ref,
            definition_id,
            origin_id,
        )
        contributions.append(
            NumericRuleContribution(
                provider_state_id,
                source,
                NumericOperation.ADD,
                value,
            )
        )
    contributions.extend(
        NumericRuleContribution(
            provider_state_id,
            source,
            NumericOperation.ADD,
            rule_effect.value,
        )
        for provider_state_id, source, rule_effect in ongoing_rule_effects(
            state, creature_ref
        )
        if isinstance(rule_effect, ArmorClassAdjustment)
    )
    return NumericRuleResult(base, tuple(contributions))


def effective_speed(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> NumericRuleResult:
    """Return effective Speed after additions, multipliers, and caps.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     speed_modifier_sources={},
    ...     attributes=SimpleNamespace(
    ...         movement=SimpleNamespace(effective_speed_feet=30)
    ...     ),
    ...     condition_immunities=lambda: frozenset(),
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(creature=creature)},
    ...     ongoing_effects=[], conditions=[],
    ... )
    >>> effective_speed(state, "hero").value
    30
    """

    creature = state.creatures[creature_ref].creature
    contributions: list[NumericRuleContribution] = []
    for definition_id, sources in creature.speed_modifier_sources.items():
        if not sources:
            continue
        origin_id, feet = max(
            sources.items(),
            key=lambda item: (item[1], item[0]),
        )
        provider_state_id, source = legacy_modifier_provider(
            state,
            creature_ref,
            definition_id,
            origin_id,
        )
        contributions.append(
            NumericRuleContribution(
                provider_state_id,
                source,
                NumericOperation.ADD,
                feet,
            )
        )
    for provider_state_id, source, rule_effect in ongoing_rule_effects(
        state, creature_ref
    ):
        if isinstance(rule_effect, SpeedAdjustment):
            contributions.append(
                NumericRuleContribution(
                    provider_state_id,
                    source,
                    NumericOperation.ADD,
                    rule_effect.feet,
                )
            )
        elif isinstance(rule_effect, SpeedMultiplier):
            contributions.append(
                NumericRuleContribution(
                    provider_state_id,
                    source,
                    NumericOperation.MULTIPLY,
                    rule_effect.numerator,
                    rule_effect.denominator,
                )
            )
    applied_conditions = tuple(
        condition
        for condition in state.conditions
        if condition.target_ref == creature_ref
    )
    conditions = effective_conditions(
        applied_conditions,
        creature.condition_immunities(),
    )
    for provider_state_id in conditions.providers_for_trait(CombatTrait.SPEED_ZERO):
        condition = next(
            condition
            for condition in applied_conditions
            if condition.id == provider_state_id
        )
        contributions.append(
            NumericRuleContribution(
                provider_state_id,
                condition.identity.source,
                NumericOperation.UPPER_CAP,
                0,
            )
        )
    return NumericRuleResult(
        creature.attributes.movement.effective_speed_feet,
        tuple(contributions),
        minimum=0,
    )


def movement_budget(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> MovementQueryResult:
    """Translate effective Speed into the encounter grid's movement budget.

    >>> from types import SimpleNamespace
    >>> from ...geometry import Grid
    >>> creature = SimpleNamespace(
    ...     speed_modifier_sources={},
    ...     attributes=SimpleNamespace(
    ...         movement=SimpleNamespace(effective_speed_feet=30)
    ...     ),
    ...     condition_immunities=lambda: frozenset(),
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(creature=creature)},
    ...     ongoing_effects=[], conditions=[],
    ...     definition=SimpleNamespace(grid=Grid(10, 10)),
    ... )
    >>> movement_budget(state, "hero").budget
    6
    """

    speed = effective_speed(state, creature_ref)
    return MovementQueryResult(
        speed=speed,
        budget=state.definition.grid.movement_budget(speed.value),
    )


def attack_limit(
    state: EncounterState,
    creature_ref: CreatureRef,
    base: int,
) -> NumericRuleResult:
    """Return the maximum attacks allowed by one Attack action.

    >>> from types import SimpleNamespace
    >>> attack_limit(SimpleNamespace(ongoing_effects=[]), "hero", 3).value
    3
    """

    contributions = tuple(
        NumericRuleContribution(
            provider_state_id,
            source,
            NumericOperation.UPPER_CAP,
            rule_effect.maximum,
        )
        for provider_state_id, source, rule_effect in ongoing_rule_effects(
            state, creature_ref
        )
        if isinstance(rule_effect, AttackLimit)
    )
    return NumericRuleResult(base, contributions, minimum=0)
