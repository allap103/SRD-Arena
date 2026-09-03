"""Adapt encounter services to the narrow spell-resolution environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from srd_arena.domain.effects.triggered import ability_modifier_contributions
from srd_arena.domain.geometry import build_radius_area
from srd_arena.domain.rolls.dice import D20RollMode, ResolvedRollModifier
from srd_arena.domain.rolls.saving_throws import Ability
from srd_arena.domain.spells.resolution import SpellTargetContext

from ...rule_queries.defenses import apply_damage
from ...rule_queries.health import apply_healing
from ...rule_queries.rolls import roll_modifiers
from ...spatial import creature_position
from ..option_discovery.spell_areas import targets_in_area

if TYPE_CHECKING:
    from srd_arena.domain.creatures import Creature
    from srd_arena.domain.spells import Spell

    from ...encounter import EncounterState


@dataclass(frozen=True)
class EncounterSpellResolutionEnvironment:
    """Expose only the live encounter operations needed to resolve one spell."""

    state: EncounterState
    actor: Creature
    actor_ref: str
    spell: Spell

    def roll_die(self, sides: int) -> int:
        """Roll one die through the encounter's injected random source."""

        return self.state.dice.roll_die(sides)

    def attack_roll_modifier(self, _target_ref: str) -> int:
        """Resolve sourced attack modifiers for the spell's caster."""

        return roll_modifiers(
            self.state,
            self.actor_ref,
            "attack_roll",
        ).resolve_modifier(self.roll_die)

    def damage_roll_modifier(self) -> ResolvedRollModifier:
        """Resolve ongoing and intrinsic modifiers for this spell's damage."""

        ongoing = roll_modifiers(
            self.state,
            self.actor_ref,
            "damage_roll",
        )
        intrinsic = ability_modifier_contributions(
            self.actor.triggered_effects,
            "spell_damage_roll",
            {"spell_id": self.spell.id},
            self._ability_modifier,
        )
        return ResolvedRollModifier(
            value=ongoing.resolve_modifier(self.roll_die)
            + sum(contribution.value for contribution in intrinsic),
            source_ids=(
                *(
                    contribution.provider_state_id
                    for contribution in ongoing.contributions
                ),
                *(contribution.source_id for contribution in intrinsic),
            ),
        )

    def _ability_modifier(self, ability: str) -> int:
        """Return the actor's modifier for one fully named ability."""

        if ability not in {
            "strength",
            "dexterity",
            "constitution",
            "intelligence",
            "wisdom",
            "charisma",
        }:
            raise ValueError(f"Unknown ability for damage modifier: {ability!r}.")
        score = self.actor.saving_throw_ability_score(cast(Ability, ability))
        return self.actor.get_modifier(score)

    def saving_throw_modifier(self, target_ref: str, ability: str) -> int:
        """Resolve sourced saving-throw modifiers for one target."""

        return roll_modifiers(
            self.state,
            target_ref,
            "saving_throw",
            ability=ability,
        ).resolve_modifier(self.roll_die)

    def saving_throw_mode(self, target_ref: str, ability: str) -> D20RollMode:
        """Resolve sourced saving-throw modes for one target."""

        return roll_modifiers(
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

        return apply_damage(
            self.state,
            target_ref,
            amount,
            damage_type,
        )

    def apply_healing(self, target_ref: str, amount: int) -> int:
        """Apply encounter-adjusted spell healing to one target."""

        return apply_healing(
            self.state,
            target_ref,
            amount,
        )

    def grant_temporary_hit_points(self, target_ref: str, amount: int) -> int:
        """Grant temporary Hit Points to one encounter participant."""

        return self.state.creatures[target_ref].creature.grant_temporary_hit_points(
            amount
        )
