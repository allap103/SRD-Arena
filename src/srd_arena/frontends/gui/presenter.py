"""Qt-independent orchestration for one interactive GUI game."""

from __future__ import annotations

from dataclasses import dataclass

from srd_arena.application.api import (
    ActionObservation,
    AimAction,
    CancelTargeting,
    ChangeTarget,
    GameCommand,
    GameObservation,
    GameUpdate,
    ConfirmTargeting,
    RunningGame,
    SelectAction,
    SetResourceAllocation,
)

from .ui.encounter.config import TargetSelectionMode
from .ui.encounter.targeting import (
    completed_allocation_action,
    mode_for_action,
)


@dataclass(frozen=True)
class ActionSelection:
    """Accepted action update plus the option that initiated it."""

    update: GameUpdate
    selected_action: ActionObservation | None


class GamePresenter:
    """Own application interaction state on behalf of the PySide6 view."""

    def __init__(self, game: RunningGame) -> None:
        self._game = game
        self._observation = game.observe()
        self._pending_target_mode: TargetSelectionMode | None = None

    @property
    def observation(self) -> GameObservation:
        """Return the latest immutable application observation."""

        return self._observation

    def refresh(self) -> GameObservation:
        """Refresh and return the current application observation."""

        self._observation = self._game.observe()
        return self._observation

    def select_action(self, action_id: str) -> ActionSelection | None:
        """Select an action and establish any resulting targeting mode."""

        selected_action = next(
            (
                action
                for action in self._observation.scene.action_details
                if action.id == action_id
            ),
            None,
        )
        self.clear_target_mode()
        update = self._execute(
            SelectAction(
                action_id=action_id,
                expected_decision_id=self.current_decision_id,
            )
        )
        if update is None:
            return None

        completed_allocation = completed_allocation_action(update.observation)
        if completed_allocation is not None:
            confirmed = self.confirm_targeting()
            if confirmed is not None:
                update = confirmed
        elif selected_action is not None and selected_action.kind == "toggle_spell_target":
            self._pending_target_mode = mode_for_action(selected_action)
        elif (
            selected_action is not None
            and selected_action.kind == "spell"
            and update.observation.encounter is not None
            and update.observation.encounter.decision.kind == "spell_targets"
        ):
            self._pending_target_mode = TargetSelectionMode(
                kind="toggle_spell_target",
                source_trigger_id=selected_action.source_id,
            )
        return ActionSelection(update=update, selected_action=selected_action)

    def aim_action(self, action_id: str, x: float, y: float) -> GameUpdate | None:
        """Aim one currently advertised area action."""

        decision_id = self.current_decision_id
        if decision_id is None:
            return None
        self.clear_target_mode()
        return self._execute(
            AimAction(
                action_id=action_id,
                x=x,
                y=y,
                expected_decision_id=decision_id,
            )
        )

    def change_target(
        self,
        target_ref: str,
        *,
        remove: bool,
        source_trigger_id: str | None,
    ) -> GameUpdate | None:
        """Add or remove one target from the active staged selection."""

        update = self._execute(
            ChangeTarget(
                target_ref=target_ref,
                remove=remove,
                expected_decision_id=self._required_decision_id(),
                source_trigger_id=source_trigger_id,
            )
        )
        if update is None:
            return None
        if completed_allocation_action(update.observation) is None:
            return update
        confirmed = self.confirm_targeting()
        return confirmed or update

    def set_resource_allocation(
        self,
        target_ref: str,
        amount: int,
    ) -> GameUpdate | None:
        """Set one target's share of the active resource allocation."""

        decision_id = self.current_decision_id
        if decision_id is None:
            return None
        return self._execute(
            SetResourceAllocation(
                target_ref=target_ref,
                amount=amount,
                expected_decision_id=decision_id,
            )
        )

    def confirm_targeting(self) -> GameUpdate | None:
        """Confirm the active staged target selection."""

        update = self._execute(
            ConfirmTargeting(
                expected_decision_id=self._required_decision_id(),
            )
        )
        if update is not None:
            self.clear_target_mode()
        return update

    def cancel_targeting(self) -> GameUpdate | None:
        """Cancel the active staged target selection."""

        update = self._execute(
            CancelTargeting(
                expected_decision_id=self._required_decision_id(),
            )
        )
        if update is not None:
            self.clear_target_mode()
        return update

    def advance_automatic(self) -> GameUpdate:
        """Advance one paced automatic step and retain its observation."""

        update = self._game.advance_automatic()
        self._observation = update.observation
        return update

    @property
    def current_decision_id(self) -> str | None:
        """Return the decision identity used for stale-input rejection."""

        encounter = self._observation.encounter
        return encounter.decision.id if encounter is not None else None

    @property
    def pending_target_mode(self) -> TargetSelectionMode | None:
        """Return the targeting mode currently represented by battlefield clicks."""

        return self._pending_target_mode

    def set_target_mode(self, mode: TargetSelectionMode | None) -> None:
        """Select a specific battlefield targeting mode."""

        self._pending_target_mode = mode

    def toggle_target_mode(self, mode: TargetSelectionMode) -> None:
        """Toggle one battlefield targeting mode."""

        self._pending_target_mode = (
            None if self._pending_target_mode == mode else mode
        )

    def clear_target_mode(self) -> None:
        """Clear transient battlefield targeting."""

        self._pending_target_mode = None

    def _required_decision_id(self) -> str:
        decision_id = self.current_decision_id
        if decision_id is None:
            raise RuntimeError("No encounter decision is active.")
        return decision_id

    def _execute(self, command: GameCommand) -> GameUpdate | None:
        result = self._game.execute(command)
        if result.update is None:
            self.refresh()
            return None
        self._observation = result.update.observation
        return result.update
