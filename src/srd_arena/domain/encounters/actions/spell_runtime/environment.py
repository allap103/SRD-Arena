"""Adapt encounter services to the narrow spell-resolution environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ....geometry import build_radius_area
from ....rolls.dice import D20RollMode
from ....spells.resolution import SpellTargetContext
from ...state_runtime import creature_position
from ..option_discovery.spell_areas import targets_in_area

if TYPE_CHECKING:
    from ....creatures import Creature
    from ...encounter import EncounterState


@dataclass(frozen=True)
class EncounterSpellResolutionEnvironment:
    """Expose only the live encounter operations needed to resolve one spell."""

    state: EncounterState
    actor: Creature
    actor_ref: str

    def roll_die(self, sides: int) -> int:
        """Roll one die through the encounter's injected random source."""

        return self.state.dice.roll_die(sides)

    def attack_roll_modifier(self, _target_ref: str) -> int:
        """Resolve sourced attack modifiers for the spell's caster."""

        return self.state.combat_rules.roll_modifiers(
            self.state,
            self.actor_ref,
            "attack_roll",
        ).resolve_modifier(self.roll_die)

    def attack_roll_mode(self, _target_ref: str) -> D20RollMode:
        """Resolve sourced attack modes for the spell's caster."""

        return self.state.combat_rules.roll_modifiers(
            self.state,
            self.actor_ref,
            "attack_roll",
        ).mode

    def damage_roll_modifier(self) -> int:
        """Resolve sourced damage modifiers for the spell's caster."""

        return self.state.combat_rules.roll_modifiers(
            self.state,
            self.actor_ref,
            "damage_roll",
        ).resolve_modifier(self.roll_die)

    def saving_throw_modifier(self, target_ref: str, ability: str) -> int:
        """Resolve sourced saving-throw modifiers for one target."""

        return self.state.combat_rules.roll_modifiers(
            self.state,
            target_ref,
            "saving_throw",
            ability=ability,
        ).resolve_modifier(self.roll_die)

    def saving_throw_mode(self, target_ref: str, ability: str) -> D20RollMode:
        """Resolve sourced saving-throw modes for one target."""

        return self.state.combat_rules.roll_modifiers(
            self.state,
            target_ref,
            "saving_throw",
            ability=ability,
        ).mode

    def targets_in_radius(
        self,
        center_ref: str,
        radius_feet: int,
    ) -> tuple[SpellTargetContext, ...]:
        """Resolve living targets in a creature-centered radius."""

        radius = int(
            self.state.definition.grid.distance_from_feet(
                radius_feet,
                minimum=1,
            )
        )
        area = build_radius_area(
            creature_position(self.state, center_ref),
            radius,
            self.state.definition.grid,
        )
        return tuple(targets_in_area(self.state, self.actor, area))

    def apply_damage(
        self,
        target_ref: str,
        amount: int,
        damage_type: str | None,
    ) -> int:
        """Apply encounter-adjusted spell damage to one target."""

        return self.state.combat_rules.apply_damage(
            self.state,
            target_ref,
            amount,
            damage_type,
        )

    def apply_healing(self, target_ref: str, amount: int) -> int:
        """Apply encounter-adjusted spell healing to one target."""

        return self.state.combat_rules.apply_healing(
            self.state,
            target_ref,
            amount,
        )

    def grant_temporary_hit_points(self, target_ref: str, amount: int) -> int:
        """Grant temporary Hit Points to one encounter participant."""

        return self.state.creatures[target_ref].creature.grant_temporary_hit_points(
            amount
        )
