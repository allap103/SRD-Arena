"""Invocation facts and live services used by spell resolution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from ...creatures import Creature
from ...geometry import AreaOfEffect
from ...rolls.dice import D20RollMode
from ..definitions import Spell


def _read_only[Key, Value](
    values: Mapping[Key, Value],
) -> Mapping[Key, Value]:
    """Copy a mapping into a read-only snapshot."""

    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class SpellTargetContext:
    """Identify one target and snapshot its encounter-derived spell facts."""

    creature: Creature
    target_ref: str
    target_label: str
    target_conditions: tuple[str, ...] = ()
    condition_immunities: frozenset[str] = frozenset()
    automatic_save_failures: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Detach automatic-save facts from the caller's mutable mapping."""

        object.__setattr__(
            self,
            "automatic_save_failures",
            _read_only(
                {
                    ability: tuple(providers)
                    for ability, providers in self.automatic_save_failures.items()
                }
            ),
        )

    def automatic_failure_reasons(self, ability: str) -> tuple[str, ...]:
        """Return condition-derived automatic save failures for an ability.

        >>> from srd_arena.domain.creatures import Attributes, Equipment, Inventory
        >>> creature = Creature("hero", "Hero", "", Inventory(),
        ...     Attributes(10, 1, 10, 10, 10, 10, 10, 10, 10), Equipment())
        >>> target = SpellTargetContext(creature, "hero", "Hero",
        ...     automatic_save_failures={"dexterity": ("stunned",)})
        >>> target.automatic_failure_reasons("dexterity")
        ('stunned',)
        >>> target.automatic_failure_reasons("wisdom")
        ()
        """
        return self.automatic_save_failures.get(ability, ())


class SpellResolutionEnvironment(Protocol):
    """Provide the narrow set of live operations spell resolution requires.

    Encounter adapters implement this interface without exposing their state
    object to the source-neutral spell package.
    """

    def roll_die(self, sides: int) -> int:
        """Roll one die with the requested number of sides."""

    def attack_roll_modifier(self, target_ref: str) -> int:
        """Resolve the caster's current sourced attack-roll modifier."""

    def attack_roll_mode(self, target_ref: str) -> D20RollMode:
        """Resolve the caster's current sourced attack-roll mode."""

    def damage_roll_modifier(self) -> int:
        """Resolve the caster's current sourced damage-roll modifier."""

    def saving_throw_modifier(self, target_ref: str, ability: str) -> int:
        """Resolve a target's current sourced saving-throw modifier."""

    def saving_throw_mode(self, target_ref: str, ability: str) -> D20RollMode:
        """Resolve a target's current sourced saving-throw mode."""

    def targets_in_radius(
        self,
        center_ref: str,
        radius_feet: int,
    ) -> tuple[SpellTargetContext, ...]:
        """Return living spell targets inside a radius around a creature."""

    def apply_damage(
        self,
        target_ref: str,
        amount: int,
        damage_type: str | None,
    ) -> int:
        """Apply effect-adjusted damage and return the amount dealt."""

    def apply_healing(self, target_ref: str, amount: int) -> int:
        """Apply effect-adjusted healing and return the amount restored."""

    def grant_temporary_hit_points(self, target_ref: str, amount: int) -> int:
        """Grant temporary Hit Points and return the resulting amount."""


@dataclass(frozen=True)
class SpellActionContext:
    """Supply read-only invocation facts plus one explicit live environment.

    The encounter copies collection-valued facts into read-only mappings before
    resolution. Live randomness, rule queries, spatial lookup, and health
    mutation cross the required :class:`SpellResolutionEnvironment` boundary
    instead of being represented by optional callbacks or direct encounter
    access.
    """

    creature: Creature
    spell: Spell
    target: SpellTargetContext
    current_round: int
    source_ref: str
    environment: SpellResolutionEnvironment
    targets: tuple[SpellTargetContext, ...] = ()
    area: AreaOfEffect | None = None
    selected_condition: str | None = None
    selected_damage_type: str | None = None
    selected_ability: str | None = None
    attack_roll_modes: Mapping[str, D20RollMode] = field(default_factory=dict)
    target_armor_classes: Mapping[str, int] = field(default_factory=dict)
    automatic_critical_providers: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    cast_level: int | None = None
    save_roll_modes: Mapping[str, D20RollMode] = field(default_factory=dict)
    healing_allocations: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Detach all mapping facts from their mutable construction inputs."""

        for name in (
            "attack_roll_modes",
            "target_armor_classes",
            "automatic_critical_providers",
            "save_roll_modes",
            "healing_allocations",
        ):
            values = getattr(self, name)
            object.__setattr__(self, name, _read_only(values))
