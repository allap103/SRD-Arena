"""Qt-independent orchestration for one interactive GUI game."""

from __future__ import annotations

from dataclasses import dataclass

from srd_arena.engine.api import (
    ActionObservation,
    AimAction,
    CancelTargeting,
    ChangeTarget,
    ConfirmTargeting,
    GameCommand,
    GameObservation,
    GameUpdate,
    SelectAction,
    Session,
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
    """Own engine interaction state on behalf of the PySide6 view."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._observation = session.observe()
        self._pending_target_mode: TargetSelectionMode | None = None

    @property
    def observation(self) -> GameObservation:
        """Return the latest immutable engine observation.

        >>> from unittest.mock import Mock
        >>> snapshot, game = Mock(), Mock()
        >>> game.observe.return_value = snapshot
        >>> GamePresenter(game).observation is snapshot
        True
        """

        return self._observation

    def refresh(self) -> GameObservation:
        """Refresh and return the current engine observation.

        >>> from unittest.mock import Mock
        >>> first, second, game = Mock(), Mock(), Mock()
        >>> game.observe.side_effect = (first, second)
        >>> presenter = GamePresenter(game)
        >>> presenter.refresh() is second
        True
        """

        self._observation = self._session.observe()
        return self._observation

    def select_action(self, action_id: str) -> ActionSelection | None:
        """Select an action and establish any resulting targeting mode.

        >>> from unittest.mock import Mock
        >>> spell = ActionObservation(
        ...     "fireball", "Fireball", "spell", "mage", source_id="fireball"
        ... )
        >>> observation = Mock(scene=Mock(action_details=(spell,)),
        ...     encounter=Mock(decision=Mock(id="turn:1"), targeting=None))
        >>> targeting_observation = Mock(
        ...     encounter=Mock(
        ...         decision=Mock(id="targets:1", kind="spell_targets"), targeting=None
        ...     )
        ... )
        >>> update, game = Mock(observation=targeting_observation), Mock()
        >>> game.observe.return_value = observation
        >>> game.execute.return_value = Mock(update=update)
        >>> presenter = GamePresenter(game)
        >>> selection = presenter.select_action("fireball")
        >>> selection.update is update if selection else False
        True
        >>> presenter.pending_target_mode
        TargetSelectionMode(kind='toggle_spell_target', source_trigger_id='fireball', variant_id=None)
        """

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
        elif (
            selected_action is not None
            and selected_action.kind == "toggle_spell_target"
        ):
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
        """Aim one currently advertised area action.

        >>> from unittest.mock import Mock
        >>> observation = Mock(encounter=Mock(decision=Mock(id="turn:1")))
        >>> update, game = Mock(observation=observation), Mock()
        >>> game.observe.return_value = observation
        >>> game.execute.return_value = Mock(update=update)
        >>> presenter = GamePresenter(game)
        >>> presenter.set_target_mode(TargetSelectionMode("spell", "fireball"))
        >>> presenter.aim_action("fireball", 2.5, 3.5) is update
        True
        >>> command = game.execute.call_args.args[0]
        >>> (command.action_id, command.x, command.y, command.expected_decision_id)
        ('fireball', 2.5, 3.5, 'turn:1')
        >>> presenter.pending_target_mode is None
        True
        """

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
        """Add or remove one target from the active staged selection.

        >>> from unittest.mock import Mock
        >>> observation = Mock(scene=Mock(action_details=()),
        ...     encounter=Mock(decision=Mock(id="targets:1"), targeting=None))
        >>> update, game = Mock(observation=observation), Mock()
        >>> game.observe.return_value = observation
        >>> game.execute.return_value = Mock(update=update)
        >>> result = GamePresenter(game).change_target(
        ...     "goblin", remove=False, source_trigger_id="eldritch_blast")
        >>> result is update
        True
        """

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
        """Set one target's share of the active resource allocation.

        >>> from unittest.mock import Mock
        >>> observation = Mock(encounter=Mock(decision=Mock(id="targets:1")))
        >>> update, game = Mock(observation=observation), Mock()
        >>> game.observe.return_value = observation
        >>> game.execute.return_value = Mock(update=update)
        >>> GamePresenter(game).set_resource_allocation("ally", 10) is update
        True
        """

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
        """Confirm the active staged target selection and clear click mode.

        >>> from unittest.mock import Mock
        >>> observation = Mock(encounter=Mock(decision=Mock(id="targets:1")))
        >>> update, game = Mock(observation=observation), Mock()
        >>> game.observe.return_value = observation
        >>> game.execute.return_value = Mock(update=update)
        >>> presenter = GamePresenter(game)
        >>> presenter.set_target_mode(TargetSelectionMode("spell"))
        >>> presenter.confirm_targeting() is update and presenter.pending_target_mode is None
        True
        """

        update = self._execute(
            ConfirmTargeting(
                expected_decision_id=self._required_decision_id(),
            )
        )
        if update is not None:
            self.clear_target_mode()
        return update

    def cancel_targeting(self) -> GameUpdate | None:
        """Cancel staged targeting and clear battlefield click mode.

        >>> from unittest.mock import Mock
        >>> observation = Mock(encounter=Mock(decision=Mock(id="targets:1")))
        >>> update, game = Mock(observation=observation), Mock()
        >>> game.observe.return_value = observation
        >>> game.execute.return_value = Mock(update=update)
        >>> presenter = GamePresenter(game)
        >>> presenter.set_target_mode(TargetSelectionMode("spell"))
        >>> presenter.cancel_targeting() is update and presenter.pending_target_mode is None
        True
        """

        update = self._execute(
            CancelTargeting(
                expected_decision_id=self._required_decision_id(),
            )
        )
        if update is not None:
            self.clear_target_mode()
        return update

    def advance_one_automatic_action(self) -> GameUpdate:
        """Resolve one automatic action and retain its observation.

        >>> from unittest.mock import Mock
        >>> first, second, game = Mock(), Mock(), Mock()
        >>> game.observe.return_value = first
        >>> update = Mock(observation=second)
        >>> game.advance_one_automatic_action.return_value = update
        >>> presenter = GamePresenter(game)
        >>> presenter.advance_one_automatic_action() is update and presenter.observation is second
        True
        """

        update = self._session.advance_one_automatic_action()
        self._observation = update.observation
        return update

    def advance_until_input_required(self) -> GameUpdate:
        """Resolve automatic actions immediately and retain the observation.

        >>> from unittest.mock import Mock
        >>> first, second, game = Mock(), Mock(), Mock()
        >>> game.observe.return_value = first
        >>> update = Mock(observation=second)
        >>> game.advance_until_input_required.return_value = update
        >>> presenter = GamePresenter(game)
        >>> presenter.advance_until_input_required() is update
        True
        >>> presenter.observation is second
        True
        """

        update = self._session.advance_until_input_required()
        self._observation = update.observation
        return update

    @property
    def current_decision_id(self) -> str | None:
        """Return the decision identity used for stale-input rejection.

        >>> from unittest.mock import Mock
        >>> game = Mock()
        >>> game.observe.return_value = Mock(
        ...     encounter=Mock(decision=Mock(id="turn:4")))
        >>> GamePresenter(game).current_decision_id
        'turn:4'
        """

        encounter = self._observation.encounter
        return encounter.decision.id if encounter is not None else None

    @property
    def pending_target_mode(self) -> TargetSelectionMode | None:
        """Return the targeting mode represented by battlefield clicks.

        >>> from unittest.mock import Mock
        >>> game = Mock()
        >>> game.observe.return_value = Mock()
        >>> presenter = GamePresenter(game)
        >>> presenter.pending_target_mode is None
        True
        """

        return self._pending_target_mode

    def set_target_mode(self, mode: TargetSelectionMode | None) -> None:
        """Select a specific battlefield targeting mode.

        >>> from unittest.mock import Mock
        >>> game = Mock()
        >>> game.observe.return_value = Mock()
        >>> presenter = GamePresenter(game)
        >>> presenter.set_target_mode(TargetSelectionMode("attack"))
        >>> presenter.pending_target_mode.kind
        'attack'
        """

        self._pending_target_mode = mode

    def toggle_target_mode(self, mode: TargetSelectionMode) -> None:
        """Toggle one battlefield targeting mode.

        >>> from unittest.mock import Mock
        >>> game = Mock()
        >>> game.observe.return_value = Mock()
        >>> presenter, mode = GamePresenter(game), TargetSelectionMode("attack")
        >>> presenter.toggle_target_mode(mode)
        >>> presenter.toggle_target_mode(mode)
        >>> presenter.pending_target_mode is None
        True
        """

        self._pending_target_mode = None if self._pending_target_mode == mode else mode

    def clear_target_mode(self) -> None:
        """Clear transient battlefield targeting.

        >>> from unittest.mock import Mock
        >>> game = Mock()
        >>> game.observe.return_value = Mock()
        >>> presenter = GamePresenter(game)
        >>> presenter.set_target_mode(TargetSelectionMode("attack"))
        >>> presenter.clear_target_mode()
        >>> presenter.pending_target_mode is None
        True
        """

        self._pending_target_mode = None

    def _required_decision_id(self) -> str:
        decision_id = self.current_decision_id
        if decision_id is None:
            raise RuntimeError("No encounter decision is active.")
        return decision_id

    def _execute(self, command: GameCommand) -> GameUpdate | None:
        result = self._session.execute(command)
        if result.update is None:
            self.refresh()
            return None
        self._observation = result.update.observation
        return result.update
