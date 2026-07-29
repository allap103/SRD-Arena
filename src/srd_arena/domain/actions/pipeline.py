from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..creatures import Creature
from ..encounters.models import EncounterAction, EncounterProgress
from .eligibility import ActionEligibility, evaluate_action

if TYPE_CHECKING:
    from ..encounters.encounter import EncounterState


@dataclass
class ActionExecutionContext:
    state: EncounterState
    player: Creature
    action: EncounterAction
    progress: EncounterProgress
    action_id: str | None = None


ActionResolver = Callable[[ActionExecutionContext], None]


class ActionPipeline:
    """Orchestrate the lifecycle shared by normal player actions."""

    def execute(
        self,
        state: EncounterState,
        player: Creature,
        action: EncounterAction,
        resolver: ActionResolver,
        *,
        expected_controller: str = "user",
        check_transition: bool = True,
        complete: bool = True,
    ) -> EncounterProgress:
        context = ActionExecutionContext(
            state=state,
            player=player,
            action=action,
            progress=EncounterProgress(),
        )
        eligibility = self.validate(
            context,
            expected_controller=expected_controller,
        )
        if not eligibility.allowed:
            self.reject(context, eligibility)
            return context.progress

        self.declare(context)
        resolver(context)
        if check_transition:
            self.check_transition(context)
        if complete:
            self.complete(context)
        return context.progress

    def validate(
        self,
        context: ActionExecutionContext,
        *,
        expected_controller: str = "user",
    ) -> ActionEligibility:
        return evaluate_action(
            context.state,
            context.player,
            context.action,
            expected_controller=expected_controller,
        )

    def reject(
        self,
        context: ActionExecutionContext,
        eligibility: ActionEligibility,
    ) -> None:
        reason = eligibility.primary_reason or "That action is not available."
        context.progress.messages.append(("system", reason))
        context.progress.events.append(
            context.state._event(
                "action_rejected",
                actor_ref=context.action.actor_ref,
                data={
                    "kind": context.action.kind,
                    "selected_action_id": context.action.id,
                    "reasons": list(eligibility.reasons),
                },
            )
        )

    def declare(self, context: ActionExecutionContext) -> None:
        context.action_id = context.state._next_action_id()
        context.progress.events.append(
            context.state._event(
                "action_declared",
                actor_ref=context.action.actor_ref,
                action_id=context.action_id,
                data={
                    "kind": context.action.kind,
                    "value": context.action.value,
                    "selected_action_id": context.action.id,
                },
            )
        )

    def check_transition(self, context: ActionExecutionContext) -> None:
        context.progress.transition = context.state._check_transition()

    def complete(self, context: ActionExecutionContext) -> None:
        if (
            context.progress.transition is not None
            or context.player.get_health() <= 0
            or context.action.kind != "wait"
        ):
            return
        context.state._advance_turn()
        context.state._maybe_reset_reactions()
        follow_up = context.state.advance_until_next_decision(context.player)
        context.state._merge_progress(context.progress, follow_up)


ACTION_PIPELINE = ActionPipeline()
