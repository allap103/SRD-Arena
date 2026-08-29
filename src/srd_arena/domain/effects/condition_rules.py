"""Project stored condition applications into their effective rule state."""

from __future__ import annotations

from dataclasses import dataclass

from .conditions import AppliedCondition, CombatTrait, Condition


@dataclass(frozen=True)
class ConditionDefinition:
    """Describe conditions and reusable combat traits implied by a condition.

    This is static rules knowledge. It does not identify a creature, source,
    duration, or individual runtime application.
    """

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
    """Aggregate the runtime applications currently providing one condition."""

    condition: Condition
    provider_ids: tuple[str, ...]


@dataclass(frozen=True)
class EffectiveTrait:
    """Aggregate the condition applications currently providing one rule trait."""

    trait: CombatTrait
    provider_ids: tuple[str, ...]


@dataclass(frozen=True)
class SuppressedCondition:
    """Record a condition excluded from the effective projection and why.

    This currently captures immunity encountered while expanding a stored
    condition into implied conditions and traits; it is diagnostic query data,
    not a dormant condition waiting to activate later.
    """

    condition: Condition
    provider_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class EffectiveConditionSet:
    """Provide a derived, source-aware view of a creature's condition rules.

    Encounter state stores individual :class:`AppliedCondition` instances.
    Rule queries use this projection to collapse duplicate effects, expand
    implied conditions, and retain the providers responsible for each result.
    """

    conditions: tuple[EffectiveCondition, ...]
    traits: tuple[EffectiveTrait, ...]
    suppressed_conditions: tuple[SuppressedCondition, ...] = ()

    def has(self, condition: Condition) -> bool:
        """Return whether a condition is currently effective.

        >>> state = EffectiveConditionSet((EffectiveCondition(Condition.PRONE, ("a",)),), ())
        >>> state.has(Condition.PRONE)
        True
        """
        return any(entry.condition is condition for entry in self.conditions)

    def has_trait(self, trait: CombatTrait) -> bool:
        """Return whether any effective condition supplies a combat trait.

        >>> state = EffectiveConditionSet((), (EffectiveTrait(CombatTrait.SPEED_ZERO, ("a",)),))
        >>> state.has_trait(CombatTrait.SPEED_ZERO)
        True
        """
        return any(entry.trait is trait for entry in self.traits)

    def providers_for(self, condition: Condition) -> tuple[str, ...]:
        """Return the runtime states providing an effective condition.

        >>> state = EffectiveConditionSet((EffectiveCondition(Condition.PRONE, ("fall",)),), ())
        >>> state.providers_for(Condition.PRONE)
        ('fall',)
        """
        return next(
            (
                entry.provider_ids
                for entry in self.conditions
                if entry.condition is condition
            ),
            (),
        )

    def providers_for_trait(self, trait: CombatTrait) -> tuple[str, ...]:
        """Return the runtime states providing an effective trait.

        >>> trait = EffectiveTrait(CombatTrait.SPEED_ZERO, ("grapple",))
        >>> EffectiveConditionSet((), (trait,)).providers_for_trait(CombatTrait.SPEED_ZERO)
        ('grapple',)
        """
        return next(
            (entry.provider_ids for entry in self.traits if entry.trait is trait),
            (),
        )


def effective_conditions(
    applied_conditions: tuple[AppliedCondition, ...],
    suppressed_conditions: frozenset[Condition] = frozenset(),
) -> EffectiveConditionSet:
    """Expand applied conditions, omitting explicitly suppressed consequences.

    >>> from srd_arena.domain.effects.conditions import build_applied_condition
    >>> paralyzed = build_applied_condition(condition=Condition.PARALYZED,
    ...     source_ref="mage", source_label="Mage", target_ref="ogre")
    >>> effective = effective_conditions((paralyzed,))
    >>> effective.has(Condition.INCAPACITATED)
    True
    >>> effective.has_trait(CombatTrait.SPEED_ZERO)
    True
    """

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
            if condition in suppressed_conditions:
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
                "suppression",
            )
            for condition, provider_ids in sorted(
                suppressed_providers.items(),
                key=lambda item: item[0].value,
            )
        ),
    )
