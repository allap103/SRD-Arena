"""Qt-independent orchestration for one interactive GUI game."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from srd_arena.engine.api import (
    ActionObservation,
    AimAction,
    CastSpell,
    GameCommand,
    GameObservation,
    GameUpdate,
    SelectAction,
    Session,
)

from .draft_commands import (
    CancelTargeting,
    ChangeTarget,
    ConfirmTargeting,
    DraftCommand,
    SetResourceAllocation,
)
from .spell_draft import SpellDraft
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

    def __init__(
        self,
        session: Session | None,
        *,
        observe: Callable[[], GameObservation] | None = None,
    ) -> None:
        if session is None and observe is None:
            raise ValueError("A session or spectator observation source is required")
        self._draft: SpellDraft | None = None
        self._session = session
        if observe is None:
            assert session is not None
            observe = session.observe
        self._observe = observe
        self._observation = observe()
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

        self._observation = self._observe()
        if self._draft is not None:
            base = self._draft.base.encounter
            current = self._observation.encounter
            if (
                base is not None
                and current is not None
                and base.decision.id == current.decision.id
            ):
                self._observation = self._draft.update().observation
            else:
                self._draft = None
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
        """Aim one currently advertised battlefield-point action.

        >>> from unittest.mock import Mock
        >>> observation = Mock(scene=Mock(action_details=()), encounter=Mock(decision=Mock(id="turn:1")))
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
        """Edit a target in the local draft; auto-submit a complete fixed allocation."""

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
        """Edit a resource share locally; no engine command is sent."""

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
        """Submit the complete local draft for engine validation and resolution."""

        update = self._execute(
            ConfirmTargeting(
                expected_decision_id=self._required_decision_id(),
            )
        )
        if update is not None:
            self.clear_target_mode()
        return update

    def cancel_targeting(self) -> GameUpdate | None:
        """Discard the local draft without changing game state."""

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

        update = self._require_session().advance_one_automatic_action()
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

        update = self._require_session().advance_until_input_required()
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

    def _execute(self, command: GameCommand | DraftCommand) -> GameUpdate | None:
        if self._draft is not None:
            draft = self._draft
            # The engine may have advanced through another controller.
            fresh = self._observe()
            if (
                fresh.encounter is None
                or draft.base.encounter is None
                or fresh.encounter.decision.id != draft.base.encounter.decision.id
            ):
                self._draft = None
                self._observation = fresh
                return None
            if isinstance(command, SelectAction):
                local = next(
                    (
                        a
                        for a in self._observation.scene.action_details
                        if a.id == command.action_id
                    ),
                    None,
                )
                if local is not None:
                    if local.kind == "toggle_spell_target":
                        command = ChangeTarget(
                            local.target_ref or "",
                            local.id.endswith("-remove"),
                            command.expected_decision_id or "",
                        )
                    elif local.kind == "confirm_spell_targets":
                        command = ConfirmTargeting(command.expected_decision_id or "")
                    elif local.kind == "cancel_spell_targets":
                        command = CancelTargeting(command.expected_decision_id or "")
            try:
                if isinstance(command, ChangeTarget):
                    draft.change_target(command.target_ref, command.remove)
                elif isinstance(command, SetResourceAllocation):
                    draft.allocate(command.target_ref, command.amount)
                elif isinstance(command, CancelTargeting):
                    self._draft = None
                    self._observation = fresh
                    return GameUpdate(fresh, (), (), None, None, False)
                elif isinstance(command, ConfirmTargeting):
                    command = draft.command()
                else:
                    return None
            except ValueError:
                return None
            if not isinstance(command, CastSpell):
                update = draft.update()
                self._observation = update.observation
                return update
        elif isinstance(command, (SelectAction, AimAction)):
            action = next(
                (
                    a
                    for a in self._observation.scene.action_details
                    if a.id == command.action_id
                ),
                None,
            )
            if action is not None and action.spell_cast is not None:
                options = action.spell_cast
                aim = (command.x, command.y) if isinstance(command, AimAction) else None
                if action.required_configuration == "aim" and aim is None:
                    return None
                if options.select_targets and aim is not None:
                    options = self._require_session().prepare_spell(
                        action.id, self._required_decision_id(), aim
                    )
                    action = replace(action, spell_cast=options)
                if options.select_targets and (
                    options.maximum_targets > 1 or options.resource_pool is not None
                ):
                    self._draft = SpellDraft(
                        self._observation,
                        action,
                        aim,
                        list(options.initial_target_refs),
                    )
                    update = self._draft.update()
                    self._observation = update.observation
                    return update
                command = CastSpell(
                    action.id,
                    self._required_decision_id(),
                    options.initial_target_refs if options.select_targets else (),
                    (),
                    aim,
                )
        if isinstance(
            command,
            (ChangeTarget, SetResourceAllocation, ConfirmTargeting, CancelTargeting),
        ):
            return None
        result = self._require_session().execute(command)
        if result.update is None:
            self.refresh()
            return None
        self._draft = None
        self._observation = result.update.observation
        return result.update

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Spectator controls cannot change the game")
        return self._session
