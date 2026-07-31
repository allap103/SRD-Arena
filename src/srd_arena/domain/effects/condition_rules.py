from __future__ import annotations

from dataclasses import dataclass

from .conditions import AppliedCondition, CombatTrait, Condition


@dataclass(frozen=True)
class ConditionDefinition:
    implied_conditions: frozenset[Condition] = frozenset()
    traits: frozenset[CombatTrait] = frozenset()


CONDITION_DEFINITIONS: dict[Condition, ConditionDefinition] = {
    Condition.INCAPACITATED: ConditionDefinition(
        traits=frozenset(
            {
                CombatTrait.CANNOT_TAKE_ACTIONS,
                CombatTrait.CANNOT_TAKE_REACTIONS,
            }
        )
    ),
    Condition.PARALYZED: ConditionDefinition(
        implied_conditions=frozenset({Condition.INCAPACITATED}),
        traits=frozenset({CombatTrait.SPEED_ZERO}),
    ),
    Condition.PETRIFIED: ConditionDefinition(
        implied_conditions=frozenset({Condition.INCAPACITATED}),
        traits=frozenset({CombatTrait.SPEED_ZERO}),
    ),
    Condition.STUNNED: ConditionDefinition(
        implied_conditions=frozenset({Condition.INCAPACITATED}),
        traits=frozenset({CombatTrait.SPEED_ZERO}),
    ),
    Condition.UNCONSCIOUS: ConditionDefinition(
        implied_conditions=frozenset({Condition.INCAPACITATED}),
    ),
    Condition.GRAPPLED: ConditionDefinition(
        traits=frozenset({CombatTrait.SPEED_ZERO}),
    ),
}


@dataclass(frozen=True)
class EffectiveCondition:
    condition: Condition
    provider_ids: tuple[str, ...]


@dataclass(frozen=True)
class EffectiveTrait:
    trait: CombatTrait
    provider_ids: tuple[str, ...]


@dataclass(frozen=True)
class EffectiveConditionSet:
    conditions: tuple[EffectiveCondition, ...]
    traits: tuple[EffectiveTrait, ...]

    def has(self, condition: Condition) -> bool:
        return any(entry.condition is condition for entry in self.conditions)

    def has_trait(self, trait: CombatTrait) -> bool:
        return any(entry.trait is trait for entry in self.traits)

    def providers_for(self, condition: Condition) -> tuple[str, ...]:
        return next(
            (
                entry.provider_ids
                for entry in self.conditions
                if entry.condition is condition
            ),
            (),
        )

    def providers_for_trait(self, trait: CombatTrait) -> tuple[str, ...]:
        return next(
            (
                entry.provider_ids
                for entry in self.traits
                if entry.trait is trait
            ),
            (),
        )


def effective_conditions(
    applied_conditions: tuple[AppliedCondition, ...],
) -> EffectiveConditionSet:
    condition_providers: dict[Condition, set[str]] = {}
    trait_providers: dict[CombatTrait, set[str]] = {}
    for applied in applied_conditions:
        expanded = _condition_closure(applied.condition)
        for condition in expanded:
            condition_providers.setdefault(condition, set()).add(applied.id)
            definition = CONDITION_DEFINITIONS.get(
                condition,
                ConditionDefinition(),
            )
            for trait in definition.traits:
                trait_providers.setdefault(trait, set()).add(applied.id)
    return EffectiveConditionSet(
        conditions=tuple(
            EffectiveCondition(condition, tuple(sorted(provider_ids)))
            for condition, provider_ids in sorted(
                condition_providers.items(),
                key=lambda item: item[0].value,
            )
        ),
        traits=tuple(
            EffectiveTrait(trait, tuple(sorted(provider_ids)))
            for trait, provider_ids in sorted(
                trait_providers.items(),
                key=lambda item: item[0].value,
            )
        ),
    )


def _condition_closure(condition: Condition) -> frozenset[Condition]:
    expanded = {condition}
    pending = [condition]
    while pending:
        current = pending.pop()
        definition = CONDITION_DEFINITIONS.get(
            current,
            ConditionDefinition(),
        )
        for implied in definition.implied_conditions:
            if implied in expanded:
                continue
            expanded.add(implied)
            pending.append(implied)
    return frozenset(expanded)
