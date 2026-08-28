"""Close decision frames and resume their typed continuations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .encounter_models.decisions import (
    CloseParentDecision,
    DecisionFrame,
    ResumeMovement,
)
from .encounter_models.resolution import EncounterProgress
from .state_runtime import create_event

if TYPE_CHECKING:
    from .encounter import EncounterState


class ContinuationRunner:
    """Drain completed decisions in strict last-in, first-out order.

    Continuations carry runtime occurrence data, rather than reusable content
    identifiers. A future spell continuation should therefore reference an
    exact invocation ID, just as movement references one suspended movement.
    """

    def complete_decision(
        self,
        state: EncounterState,
        decision: DecisionFrame,
        *,
        action_id: str,
        progress: EncounterProgress,
    ) -> None:
        """Close a decision and run its typed continuation in LIFO order.

        A decision cannot be completed after its frame has left the stack.

        >>> from unittest.mock import Mock
        >>> decision = DecisionFrame("reaction-1", "hero", "reaction", "shield")
        >>> state = Mock(interrupts=Mock(decision_stack=[]))
        >>> ContinuationRunner().complete_decision(
        ...     state, decision, action_id="decline", progress=EncounterProgress())
        Traceback (most recent call last):
        ...
        RuntimeError: Cannot close decision 'reaction-1': the stack is empty.
        """
        current = decision
        current_action_id = action_id
        while True:
            self._require_top(state, current.id)
            continuation = current.continuation
            if isinstance(continuation, CloseParentDecision):
                if continuation.frame_id != current.parent_frame_id:
                    raise RuntimeError(
                        f"Decision '{current.id}' cannot complete unrelated frame "
                        f"'{continuation.frame_id}'."
                    )
                if (
                    len(state.interrupts.decision_stack) < 2
                    or state.interrupts.decision_stack[-2].id != continuation.frame_id
                ):
                    raise RuntimeError(
                        f"Decision '{current.id}' cannot complete frame "
                        f"'{continuation.frame_id}' out of LIFO order."
                    )
            elif continuation is not None and not isinstance(
                continuation,
                ResumeMovement,
            ):
                raise TypeError(
                    "ContinuationRunner has no handler for continuation "
                    f"'{type(continuation).__name__}'."
                )

            self._pop_decision(
                state,
                expected_frame_id=current.id,
                action_id=current_action_id,
                progress=progress,
            )
            if isinstance(continuation, CloseParentDecision):
                current = state.interrupts.decision_stack[-1]
                current_action_id = continuation.action_id
                continue
            if isinstance(continuation, ResumeMovement):
                state.reaction_engine.resume_movement(
                    state,
                    continuation.movement,
                    progress,
                )
            return

    def _require_top(
        self,
        state: EncounterState,
        expected_frame_id: str,
    ) -> None:
        if not state.interrupts.decision_stack:
            raise RuntimeError(
                f"Cannot close decision '{expected_frame_id}': the stack is empty."
            )
        current = state.interrupts.decision_stack[-1]
        if current.id != expected_frame_id:
            raise RuntimeError(
                f"Cannot close decision '{expected_frame_id}' while "
                f"'{current.id}' is active."
            )

    def _pop_decision(
        self,
        state: EncounterState,
        *,
        expected_frame_id: str,
        action_id: str,
        progress: EncounterProgress,
    ) -> DecisionFrame:
        self._require_top(state, expected_frame_id)
        decision = state.interrupts.decision_stack[-1]
        state.interrupts.decision_stack.pop()
        progress.events.append(
            create_event(
                state,
                "decision_closed",
                creature_ref=decision.creature_ref,
                frame_id=decision.id,
                action_id=action_id,
            )
        )
        return decision
