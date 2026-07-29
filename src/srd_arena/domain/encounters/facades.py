from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..actions.feature_actions import FeatureActionDefinition
from ..actions.options import (
    available_actions,
    available_feature_actions,
    available_spell_actions,
    feature_action_available,
    spell_action_cost,
    spell_action_targets,
    spell_area,
    spell_area_targets,
    spell_cast_block_reason_for,
    spell_range_squares_for,
    spell_target_context,
    spell_targets_self_only_for,
    spend_spell_resources,
    targets_in_area,
)
from ..actions.player import (
    apply_action,
    apply_player_move,
    apply_user_controlled_enemy_action,
    resolve_feature_action,
    resolve_grapple_action,
    resolve_player_attack_action,
    resolve_spell_action,
    resolve_utilize_action,
    resolve_wait_action,
    user_controlled_enemy_actions,
)
from ..actions.spells.definitions import Spell
from ..actions.spells.resolution import SpellTargetContext
from ..creatures import Creature, Spellcasting
from ..effects.conditions import Status
from ..geometry import AreaOfEffect
from .conditions import (
    apply_status,
    condition_sources_for,
    grappled_sources_for,
    grappling_targets_for,
    is_grappled,
    movement_cost_for,
    remove_status,
    status_replaces,
)
from .models import (
    ActionCost,
    CreatureRef,
    DecisionFrame,
    EncounterAction,
    Combatant,
    EncounterProgress,
)
from .participants import (
    actors_are_opponents,
    creature_controller,
    creature_for_ref,
    creature_team_id,
)
from .queries import living_enemy_at, player_movement_remaining
from .serialization import export_decision, export_pending_action, export_state

if TYPE_CHECKING:
    from .encounter import EncounterState


@dataclass(frozen=True)
class EncounterActions:
    """Bound entrypoint for discovering and performing encounter actions."""

    state: EncounterState

    def available(self, actor_ref: CreatureRef) -> list[EncounterAction]:
        return available_actions(self.state, actor_ref)

    def perform(
        self,
        player: Creature,
        action: EncounterAction,
    ) -> EncounterProgress:
        return apply_action(self.state, player, action)

    def available_features(self, player: Creature) -> list[EncounterAction]:
        return available_feature_actions(self.state, player)

    def available_spells(self, player: Creature) -> list[EncounterAction]:
        return available_spell_actions(self.state, player)

    def feature_is_available(
        self, player: Creature, definition: FeatureActionDefinition
    ) -> bool:
        return feature_action_available(self.state, player, definition)

    def spell_cost(self, spell: Spell) -> ActionCost:
        return spell_action_cost(self.state, spell)

    def spell_block_reason(
        self, spellcasting: Spellcasting, spell: Spell, cost: ActionCost
    ) -> str | None:
        return spell_cast_block_reason_for(self.state, spellcasting, spell, cost)

    def spell_targets_self_only(self, spell: Spell) -> bool:
        return spell_targets_self_only_for(self.state, spell)

    def spell_range(self, spell: Spell, creature: Creature) -> int | None:
        return spell_range_squares_for(self.state, spell, creature)

    def spell_targets(
        self, player: Creature, spell: Spell
    ) -> list[SpellTargetContext]:
        return spell_action_targets(self.state, player, spell)

    def spell_area_targets(
        self,
        player: Creature,
        spell: Spell,
        target_ref: str | None = None,
        aim_point: tuple[float, float] | None = None,
    ) -> tuple[SpellTargetContext, ...]:
        return spell_area_targets(
            self.state,
            player,
            spell,
            target_ref=target_ref,
            aim_point=aim_point,
        )

    def spend_spell_resources(
        self, spellcasting: Spellcasting, spell: Spell, cost: ActionCost
    ) -> None:
        spend_spell_resources(self.state, spellcasting, spell, cost)

    def spell_area(
        self,
        player: Creature,
        spell: Spell,
        target_ref: str | None = None,
        aim_point: tuple[float, float] | None = None,
    ) -> AreaOfEffect | None:
        return spell_area(
            self.state,
            player,
            spell,
            target_ref=target_ref,
            aim_point=aim_point,
        )

    def targets_in_area(
        self, player: Creature, area: AreaOfEffect
    ) -> list[SpellTargetContext]:
        return targets_in_area(self.state, player, area)

    def spell_target(
        self, player: Creature, target_ref: str
    ) -> SpellTargetContext | None:
        return spell_target_context(self.state, player, target_ref)

    def available_for_controlled_enemy(
        self, actor_ref: CreatureRef
    ) -> list[EncounterAction]:
        return user_controlled_enemy_actions(self.state, actor_ref)

    def perform_for_controlled_enemy(
        self,
        player: Creature,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> EncounterProgress:
        return apply_user_controlled_enemy_action(
            self.state, player, action, decision
        )

    def resolve_attack(
        self,
        player: Creature,
        action: EncounterAction,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        resolve_player_attack_action(
            self.state, player, action, progress, action_id
        )

    def resolve_wait(self, progress: EncounterProgress, action_id: str) -> None:
        resolve_wait_action(self.state, progress, action_id)

    def resolve_item(
        self,
        player: Creature,
        item_id: str,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        resolve_utilize_action(self.state, player, item_id, progress, action_id)

    def resolve_feature(
        self,
        player: Creature,
        feature_id: str,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        resolve_feature_action(
            self.state, player, feature_id, progress, action_id
        )

    def resolve_spell(
        self,
        player: Creature,
        spell_value: str,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        resolve_spell_action(
            self.state, player, spell_value, progress, action_id
        )

    def resolve_grapple(
        self,
        player: Creature,
        action: EncounterAction,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        resolve_grapple_action(
            self.state, player, action, progress, action_id
        )

    def move_player(
        self,
        player: Creature,
        direction: str,
        progress: EncounterProgress,
        action_id: str,
    ) -> None:
        apply_player_move(self.state, player, direction, progress, action_id)


@dataclass(frozen=True)
class EncounterRules:
    """Bound entrypoint for conditions and encounter participant rules."""

    state: EncounterState

    def apply_status(self, status: Status) -> None:
        apply_status(self.state, status)

    def remove_status(
        self, target_ref: CreatureRef, status_name: str
    ) -> None:
        remove_status(self.state, target_ref, status_name)

    def condition_sources(
        self, actor_ref: CreatureRef, condition_name: str
    ) -> tuple[CreatureRef, ...]:
        return condition_sources_for(self.state, actor_ref, condition_name)

    def grappled_sources(
        self, actor_ref: CreatureRef
    ) -> tuple[CreatureRef, ...]:
        return grappled_sources_for(self.state, actor_ref)

    def grappling_targets(
        self, actor_ref: CreatureRef
    ) -> tuple[CreatureRef, ...]:
        return grappling_targets_for(self.state, actor_ref)

    def is_grappled(self, actor_ref: CreatureRef) -> bool:
        return is_grappled(self.state, actor_ref)

    def movement_cost(
        self, player: Creature, actor_ref: CreatureRef
    ) -> int | None:
        return movement_cost_for(self.state, player, actor_ref)

    def status_replaces(self, existing: Status, status: Status) -> bool:
        return status_replaces(existing, status)

    def controller(self, actor_ref: CreatureRef) -> str:
        return creature_controller(self.state, actor_ref)

    def team_id(self, actor_ref: CreatureRef) -> str:
        return creature_team_id(self.state, actor_ref)

    def are_opponents(
        self, first: CreatureRef, second: CreatureRef
    ) -> bool:
        return actors_are_opponents(self.state, first, second)

    def creature(
        self, player: Creature, actor_ref: CreatureRef
    ) -> Creature:
        return creature_for_ref(self.state, player, actor_ref)


@dataclass(frozen=True)
class EncounterReadModel:
    """Bound entrypoint for serialized encounter projections."""

    state: EncounterState

    def decision(self) -> dict[str, object]:
        return export_decision(self.state)

    def state_for(self, player: Creature) -> dict[str, Any]:
        return export_state(self.state, player)

    def pending_action(self) -> dict[str, object] | None:
        return export_pending_action(self.state)


@dataclass(frozen=True)
class EncounterQueries:
    """Bound gameplay queries that do not mutate encounter state."""

    state: EncounterState

    def movement_remaining(self, player: Creature) -> int:
        return player_movement_remaining(self.state, player)

    def living_enemy_at(self, x: int, y: int) -> Combatant | None:
        return living_enemy_at(self.state, x, y)
