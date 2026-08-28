"""Stable coordinator for encounter reaction mechanics.

Opportunity Attacks, damage rerolls, and attack lifecycle consequences live
in focused :mod:`reaction_runtime` modules.  This facade retains the service
API consumed by encounter orchestration and continuation handling.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from ..effects.triggered import TriggeredEffect
from ..geometry import MovementBudget, MovementCost, Position
from .encounter_models.actions import EncounterAction
from .encounter_models.decisions import (
    DecisionContinuation,
    DecisionFrame,
    PendingMovement,
)
from .encounter_models.resolution import (
    AttackOutcome,
    DamageRerollRequest,
    DecisionExecutionResult,
    EncounterProgress,
)

if TYPE_CHECKING:
    from .encounter import EncounterState

from .reaction_runtime.attack_lifecycle import (
    resolve_attack_lifecycle as _resolve_attack_lifecycle,
)
from .reaction_runtime.damage_rerolls import (
    apply_damage_reroll_action as _apply_damage_reroll_action,
)
from .reaction_runtime.damage_rerolls import (
    damage_reroll_event_data as _damage_reroll_event_data,
)
from .reaction_runtime.damage_rerolls import (
    damage_reroll_request as _damage_reroll_request,
)
from .reaction_runtime.damage_rerolls import (
    finalize_damage_reroll as _finalize_damage_reroll,
)
from .reaction_runtime.damage_rerolls import (
    open_damage_reroll_decision as _open_damage_reroll_decision,
)
from .reaction_runtime.damage_rerolls import (
    reroll_damage_actions as _reroll_damage_actions,
)
from .reaction_runtime.opportunity_attacks import (
    apply_reaction_action as _apply_reaction_action,
)
from .reaction_runtime.opportunity_attacks import (
    opportunity_attack_request as _opportunity_attack_request,
)
from .reaction_runtime.opportunity_attacks import (
    queue_opportunity_attack as _queue_opportunity_attack,
)
from .reaction_runtime.opportunity_attacks import (
    reaction_actions as _reaction_actions,
)
from .reaction_runtime.opportunity_attacks import (
    resolve_automatic_opportunity_attacks as _resolve_automatic_opportunity_attacks,
)
from .reaction_runtime.opportunity_attacks import (
    resume_movement as _resume_movement,
)


def _roll_die(sides: int) -> int:
    """Roll through the encounter module's runtime-patchable dice seam."""

    from . import encounter as encounter_module

    return encounter_module.roll_die(sides)


def _roll_dice(count: int, sides: int) -> int:
    """Roll damage through the encounter module's patchable dice seam."""

    from . import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


class ReactionEngine:
    """Coordinate reaction offers while the orchestrator owns continuation."""

    def resolve_automatic_opportunity_attacks(
        self,
        state: EncounterState,
        *,
        mover_ref: str,
        from_position: Position,
        to_position: Position,
        action_id: str,
        progress: EncounterProgress,
        excluded_reactor_refs: Collection[str] = (),
    ) -> list[tuple[str, str]]:
        """Resolve eligible scripted Opportunity Attacks without pausing.

        >>> from unittest.mock import Mock
        >>> state = Mock(creatures={"hero": Mock()})
        >>> progress = EncounterProgress()
        >>> ReactionEngine().resolve_automatic_opportunity_attacks(
        ...     state, mover_ref="hero", from_position=Position(0, 0),
        ...     to_position=Position(1, 0), action_id="move", progress=progress)
        []
        """
        return _resolve_automatic_opportunity_attacks(
            state,
            mover_ref=mover_ref,
            from_position=from_position,
            to_position=to_position,
            action_id=action_id,
            progress=progress,
            excluded_reactor_refs=excluded_reactor_refs,
        )

    def open_damage_reroll_decision(
        self,
        state: EncounterState,
        *,
        attack: AttackOutcome,
        triggered_effect: TriggeredEffect,
        attacker_ref: str,
        target_ref: str,
        attacker_label: str,
        target_label: str,
        action_id: str,
        progress: EncounterProgress,
        continuation: DecisionContinuation | None = None,
        reaction: bool = False,
    ) -> None:
        """Suspend an attack by pushing its optional damage-reroll decision.

        >>> from unittest.mock import Mock
        >>> attack = AttackOutcome([], True, 18, 0, False, {})
        >>> trigger = TriggeredEffect("great_weapon", "feature", "great_weapon",
        ...     "damage_rolled", "reroll_matching_dice")
        >>> state = Mock(active_attacks_remaining=1, decision_stack=[])
        >>> state._next_frame_id.return_value = "reroll:1"
        >>> state.current_decision.return_value = DecisionFrame("turn", "hero", "turn", "active")
        >>> progress = EncounterProgress()
        >>> ReactionEngine().open_damage_reroll_decision(state, attack=attack,
        ...     triggered_effect=trigger, attacker_ref="hero", target_ref="ogre",
        ...     attacker_label="Hero", target_label="Ogre", action_id="attack:1",
        ...     progress=progress)
        >>> (state.decision_stack[-1].kind, progress.paused_for_decision)
        ('reroll_dice', True)
        """
        _open_damage_reroll_decision(
            state,
            attack=attack,
            triggered_effect=triggered_effect,
            attacker_ref=attacker_ref,
            target_ref=target_ref,
            attacker_label=attacker_label,
            target_label=target_label,
            action_id=action_id,
            progress=progress,
            continuation=continuation,
            reaction=reaction,
        )

    def reroll_damage_actions(self, state: EncounterState) -> list[EncounterAction]:
        """Build choices for the active optional damage-reroll decision.

        >>> from unittest.mock import Mock
        >>> trigger = TriggeredEffect("reroll", "feature", "reroll",
        ...     "damage_rolled", "reroll_matching_dice")
        >>> request = DamageRerollRequest("attack", "hero", "ogre", "Hero", "Ogre", 1,
        ...     AttackOutcome([], True, 18, 0, False, {}), trigger)
        >>> state = Mock()
        >>> state.current_decision.return_value = DecisionFrame(
        ...     "reroll:1", "hero", "reroll_dice", "reroll", request=request)
        >>> ReactionEngine().reroll_damage_actions(state)
        []
        """
        return _reroll_damage_actions(state)

    def apply_damage_reroll_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> DecisionExecutionResult:
        """Apply a reroll choice while leaving frame closure to orchestration.

        A malformed reroll request is rejected before state changes occur.

        >>> from unittest.mock import Mock
        >>> trigger = TriggeredEffect("reroll", "feature", "reroll",
        ...     "damage_rolled", "reroll_matching_dice")
        >>> request = DamageRerollRequest("attack", "hero", "ogre", "Hero", "Ogre", 1,
        ...     AttackOutcome([], True, 18, 0, False, {}), trigger)
        >>> decision = DecisionFrame("reroll:1", "hero", "reroll_dice", "reroll",
        ...     request=request)
        >>> ReactionEngine().apply_damage_reroll_action(
        ...     Mock(), EncounterAction("Accept", "accept_roll"), decision)
        Traceback (most recent call last):
        ...
        RuntimeError: Damage reroll requested without a pending attack.
        """
        return _apply_damage_reroll_action(state, action, decision)

    def finalize_damage_reroll(
        self,
        state: EncounterState,
        request: DamageRerollRequest,
        progress: EncounterProgress,
        decision: DecisionFrame,
    ) -> None:
        """Apply accepted reroll damage and record the completed attack.

        >>> from unittest.mock import Mock
        >>> trigger = TriggeredEffect("reroll", "feature", "reroll",
        ...     "damage_rolled", "reroll_matching_dice")
        >>> request = DamageRerollRequest("attack", "hero", "ogre", "Hero", "Ogre", 1,
        ...     AttackOutcome([], False, 8, 0, False, {}), trigger)
        >>> state = Mock(ongoing_effects=[], creatures={
        ...     "hero": Mock(creature=Mock(name="Hero")),
        ...     "ogre": Mock(creature=Mock(), is_alive=True)})
        >>> state._event.side_effect = lambda kind, **_details: kind
        >>> progress = EncounterProgress()
        >>> decision = DecisionFrame("reroll:1", "hero", "reroll_dice", "reroll")
        >>> ReactionEngine().finalize_damage_reroll(state, request, progress, decision)
        >>> progress.events
        ['attack_resolved']
        """
        _finalize_damage_reroll(state, request, progress, decision)

    def damage_reroll_event_data(
        self,
        request: DamageRerollRequest,
    ) -> dict[str, object]:
        """Return stable event data for a pending damage-reroll occurrence.

        >>> trigger = TriggeredEffect("reroll", "feature", "reroll",
        ...     "damage_rolled", "reroll_matching_dice")
        >>> request = DamageRerollRequest("attack", "hero", "ogre", "Hero", "Ogre", 1,
        ...     AttackOutcome([], True, 18, 0, False, {}), trigger)
        >>> ReactionEngine().damage_reroll_event_data(request)
        {}
        """
        return _damage_reroll_event_data(request)

    def apply_reaction_action(
        self,
        state: EncounterState,
        action: EncounterAction,
        decision: DecisionFrame,
    ) -> DecisionExecutionResult:
        """Resolve an offered reaction choice without closing its frame.

        >>> from unittest.mock import Mock
        >>> state = Mock(creatures={"hero": Mock()})
        >>> state._next_action_id.return_value = "reaction:1"
        >>> decision = DecisionFrame("frame:1", "hero", "reaction", "opportunity")
        >>> result = ReactionEngine().apply_reaction_action(
        ...     state, EncounterAction("Pass", "pass"), decision)
        >>> (result.completed, result.action_id)
        (True, 'reaction:1')
        """
        return _apply_reaction_action(
            state,
            action,
            decision,
            open_damage_reroll=self.open_damage_reroll_decision,
        )

    def resume_movement(
        self,
        state: EncounterState,
        movement: PendingMovement,
        progress: EncounterProgress,
    ) -> None:
        """Resume the precise movement occurrence suspended by a reaction.

        >>> from unittest.mock import Mock
        >>> mover = Mock(is_alive=True, position=Position(0, 0),
        ...     movement_spent_this_turn=MovementCost(0), creature=Mock(name="Hero"))
        >>> state = Mock(creatures={"hero": mover})
        >>> state._position_is_free.return_value = True
        >>> movement = PendingMovement("move", "hero", "right", Position(0, 0),
        ...     Position(1, 0), MovementBudget(5), MovementCost(1), "trigger")
        >>> ReactionEngine().resume_movement(state, movement, EncounterProgress())
        >>> (mover.position, mover.movement_remaining)
        (Position(x=1, y=0), 5)
        """
        _resume_movement(state, movement, progress)

    def queue_opportunity_attack(
        self,
        state: EncounterState,
        *,
        mover_ref: str,
        action_id: str,
        direction: str,
        from_position: Position,
        to_position: Position,
        remaining_movement_after: MovementBudget,
        movement_cost: MovementCost,
        companion_destinations: dict[str, Position],
        progress: EncounterProgress,
        external_only: bool,
        excluded_reactor_refs: Collection[str] = (),
    ) -> bool:
        """Open the first eligible external Opportunity Attack decision.

        >>> from unittest.mock import Mock
        >>> state = Mock(creatures={"hero": Mock()})
        >>> ReactionEngine().queue_opportunity_attack(state, mover_ref="hero",
        ...     action_id="move", direction="right", from_position=Position(0, 0),
        ...     to_position=Position(1, 0), remaining_movement_after=MovementBudget(5),
        ...     movement_cost=MovementCost(1), companion_destinations={},
        ...     progress=EncounterProgress(), external_only=True)
        False
        """
        return _queue_opportunity_attack(
            state,
            mover_ref=mover_ref,
            action_id=action_id,
            direction=direction,
            from_position=from_position,
            to_position=to_position,
            remaining_movement_after=remaining_movement_after,
            movement_cost=movement_cost,
            companion_destinations=companion_destinations,
            progress=progress,
            external_only=external_only,
            excluded_reactor_refs=excluded_reactor_refs,
        )

    def reaction_actions(self, state: EncounterState) -> list[EncounterAction]:
        """Build choices for the active reaction decision.

        Non-Opportunity-Attack reactions always retain an explicit pass choice.

        >>> from unittest.mock import Mock
        >>> state = Mock()
        >>> state.current_decision.return_value = DecisionFrame(
        ...     "reaction:1", "hero", "reaction", "counterspell")
        >>> [(action.kind, action.creature_ref)
        ...  for action in ReactionEngine().reaction_actions(state)]
        [('pass', 'hero')]
        """
        return _reaction_actions(state)


REACTION_ENGINE = ReactionEngine()

__all__ = [
    "REACTION_ENGINE",
    "ReactionEngine",
    "_damage_reroll_request",
    "_opportunity_attack_request",
    "_resolve_attack_lifecycle",
    "_roll_dice",
    "_roll_die",
]
