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
                CombatTrait.INITIATIVE_DISADVANTAGE,
            }
        )
    ),
    Condition.PARALYZED: ConditionDefinition(
        implied_conditions=frozenset({Condition.INCAPACITATED}),
        traits=frozenset(
            {
                CombatTrait.SPEED_ZERO,
                CombatTrait.ATTACKERS_HAVE_ADVANTAGE,
                CombatTrait.AUTO_FAIL_STRENGTH_SAVES,
                CombatTrait.AUTO_FAIL_DEXTERITY_SAVES,
                CombatTrait.HITS_WITHIN_5_FEET_ARE_CRITICAL,
            }
        ),
    ),
    Condition.PETRIFIED: ConditionDefinition(
        implied_conditions=frozenset({Condition.INCAPACITATED}),
        traits=frozenset({CombatTrait.SPEED_ZERO}),
    ),
    Condition.STUNNED: ConditionDefinition(
        implied_conditions=frozenset({Condition.INCAPACITATED}),
        traits=frozenset(
            {
                CombatTrait.SPEED_ZERO,
                CombatTrait.ATTACKERS_HAVE_ADVANTAGE,
                CombatTrait.AUTO_FAIL_STRENGTH_SAVES,
                CombatTrait.AUTO_FAIL_DEXTERITY_SAVES,
            }
        ),
    ),
    Condition.UNCONSCIOUS: ConditionDefinition(
        implied_conditions=frozenset({Condition.INCAPACITATED}),
        traits=frozenset(
            {
                CombatTrait.ATTACKERS_HAVE_ADVANTAGE,
                CombatTrait.AUTO_FAIL_STRENGTH_SAVES,
                CombatTrait.AUTO_FAIL_DEXTERITY_SAVES,
                CombatTrait.HITS_WITHIN_5_FEET_ARE_CRITICAL,
            }
        ),
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
class SuppressedCondition:
    condition: Condition
    provider_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class EffectiveConditionSet:
    conditions: tuple[EffectiveCondition, ...]
    traits: tuple[EffectiveTrait, ...]
    suppressed_conditions: tuple[SuppressedCondition, ...] = ()

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
            (entry.provider_ids for entry in self.traits if entry.trait is trait),
            (),
        )


def effective_conditions(
    applied_conditions: tuple[AppliedCondition, ...],
    condition_immunities: frozenset[Condition] = frozenset(),
) -> EffectiveConditionSet:
    condition_providers: dict[Condition, set[str]] = {}
    trait_providers: dict[CombatTrait, set[str]] = {}
    suppressed_providers: dict[Condition, set[str]] = {}
    for applied in applied_conditions:
        pending = [applied.condition]
        expanded: set[Condition] = set()
        while pending:
            condition = pending.pop()
            if condition in expanded:
                continue
            expanded.add(condition)
            if condition in condition_immunities:
                suppressed_providers.setdefault(condition, set()).add(applied.id)
                continue
            condition_providers.setdefault(condition, set()).add(applied.id)
            definition = CONDITION_DEFINITIONS.get(
                condition,
                ConditionDefinition(),
            )
            for trait in definition.traits:
                trait_providers.setdefault(trait, set()).add(applied.id)
            pending.extend(definition.implied_conditions)
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
        suppressed_conditions=tuple(
            SuppressedCondition(
                condition,
                tuple(sorted(provider_ids)),
                "immunity",
            )
            for condition, provider_ids in sorted(
                suppressed_providers.items(),
                key=lambda item: item[0].value,
            )
        ),
    )
