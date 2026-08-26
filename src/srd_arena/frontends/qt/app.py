from __future__ import annotations

from pathlib import Path
from ...application.commands import (
    AimAction,
    CancelTargeting,
    ChangeTarget,
    CommandResult,
    ConfirmTargeting,
    GameUpdate,
    SelectAction,
    SetResourceAllocation,
)
from ...application.game import RunningGame
from ...application.observations import (
    ActionObservation,
    EncounterObservation,
    GameObservation,
)
from ...application.scenarios import ScenarioPresentation
from ..shared.dice import build_roll_views, without_roll_details
from ..shared.models import SessionPresentation
from ..shared.session import build_session_presentation
from .ui.encounter import (
    ActionMenuScope,
    BattlefieldWidget,
    TargetSelectionMode,
    clear_layout,
)
from .ui.encounter.movement import (
    MovementPlan,
    build_movement_plan,
    movement_plan_is_current,
)
from .ui.encounter.panel_renderer import (
    EncounterPanelCallbacks,
    EncounterPanelRenderer,
)
from .ui.encounter.targeting import (
    action_for_target_click,
    allocation_counts,
    allocation_status,
    cancel_targeting_action,
    completed_allocation_action,
    mode_for_action,
    mode_is_available,
    pending_area_action,
    pending_area_overlay,
    selection_modes,
    target_creature_ref,
)
from .ui.sidebar import GameSidebar, SidebarCallbacks


try:
    from PySide6.QtCore import QSize, Qt, QTimer, Signal
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QScrollArea,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency at runtime

    def Signal(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    QApplication = None  # type: ignore[assignment]
    QSize = object  # type: ignore[assignment]
    Qt = object  # type: ignore[assignment]
    QTimer = object  # type: ignore[assignment]
    QFont = object  # type: ignore[assignment]
    QFrame = object  # type: ignore[assignment]
    QHBoxLayout = object  # type: ignore[assignment]
    QLabel = object  # type: ignore[assignment]
    QMainWindow = object  # type: ignore[assignment]
    QPushButton = object  # type: ignore[assignment]
    QScrollArea = object  # type: ignore[assignment]
    QTextEdit = object  # type: ignore[assignment]
    QVBoxLayout = object  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]
def _require_pyside6() -> None:
    if QApplication is None:
        raise RuntimeError(
            "PySide6 is not installed. Install project dependencies including PySide6 to use this frontend."
        )


class GameWindow(QMainWindow):
    def __init__(
        self,
        game: RunningGame,
        *,
        image_root: Path | None = None,
        presentation_config: ScenarioPresentation | None = None,
        show_encounter_json: bool = False,
    ):
        _require_pyside6()
        super().__init__()
        self.game = game
        self._image_root = image_root
        self._observation: GameObservation | None = None
        self._encounter_presentation_config = (
            presentation_config or ScenarioPresentation()
        )
        self._presentation: SessionPresentation | None = None
        self._pending_target_mode: TargetSelectionMode | None = None
        self._action_menu_scope: ActionMenuScope | None = None
        self._combat_log_scene_id: str | None = None
        self._logged_round_number: int | None = None
        self._automatic_step_scheduled = False
        self._show_team_outlines = True
        self._always_show_creature_names = False
        self._movement_plan: MovementPlan | None = None

        self.setWindowTitle("SRD Arena")
        self.resize(1400, 900)

        central = QWidget()
        central.setObjectName("rootCentral")
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._build_main_content(), stretch=1)
        self.sidebar = GameSidebar(
            SidebarCallbacks(
                select_log_action=self._select_action_by_id,
                end_turn=self._end_turn,
                close_window=self.close,
                set_team_outlines_visible=self._set_team_outlines_visible,
                set_creature_names_visible=self._set_always_show_creature_names,
            ),
            initiative_layout=self.initiative_layout,
            show_encounter_json=show_encounter_json,
            show_team_outlines=self._show_team_outlines,
            show_creature_names=self._always_show_creature_names,
        )
        root_layout.addWidget(self.sidebar)
        self._encounter_panel_renderer = EncounterPanelRenderer(
            self.sidebar.encounter_bindings,
            EncounterPanelCallbacks(
                select_action=self._select_action,
                toggle_target=self._toggle_target_action,
                open_action_menu=self._open_action_menu,
                close_action_menu=self._close_action_menu,
                set_resource_allocation=self._set_spell_resource_allocation,
            ),
        )

        self.refresh_view()

    def _build_main_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.scene_group = self._build_group("Scene")
        self.scene_group.setObjectName("scenePanel")
        self.scene_text = self._build_readonly_text(minimum_height=180)
        self.scene_group.layout().addWidget(self.scene_text)

        self.story_choices_group = self._build_group("Choices")
        self.story_choices_group.setObjectName("choicesPanel")
        self.story_choices_layout = QVBoxLayout()
        self.story_choices_layout.setSpacing(8)
        story_scroll = self._wrap_in_scroll(self.story_choices_layout)
        self.story_choices_group.layout().addWidget(story_scroll)

        self.encounter_panel = QWidget()
        self.encounter_panel.setObjectName("encounterPanel")
        encounter_layout = QVBoxLayout(self.encounter_panel)
        encounter_layout.setContentsMargins(0, 0, 0, 0)
        encounter_layout.setSpacing(10)

        battlefield_area = QWidget()
        battlefield_layout = QHBoxLayout(battlefield_area)
        battlefield_layout.setContentsMargins(0, 0, 0, 0)
        battlefield_layout.setSpacing(10)

        self.battlefield_widget = BattlefieldWidget(image_root=self._image_root)
        self.battlefield_widget.setObjectName("combatBoard")
        self.battlefield_widget.creature_clicked.connect(
            self._handle_battlefield_creature_clicked
        )
        self.battlefield_widget.cell_clicked.connect(
            self._handle_battlefield_cell_clicked
        )
        self.battlefield_widget.point_clicked.connect(
            self._handle_battlefield_point_clicked
        )
        self.battlefield_widget.interaction_cancelled.connect(
            self._cancel_battlefield_interaction
        )

        self.initiative_rail = QFrame()
        self.initiative_rail.setObjectName("rollRail")
        self.initiative_rail.setFrameShape(QFrame.Shape.StyledPanel)
        self.initiative_rail.setFixedWidth(110)
        initiative_layout = QVBoxLayout(self.initiative_rail)
        initiative_layout.setContentsMargins(6, 6, 6, 6)
        initiative_layout.setSpacing(4)
        initiative_title = QLabel("Initiative")
        initiative_title.setObjectName("initiativeTitle")
        initiative_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        initiative_layout.addWidget(initiative_title)
        self.initiative_scroll = QScrollArea()
        self.initiative_scroll.setWidgetResizable(True)
        self.initiative_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.initiative_content = QWidget()
        self.initiative_layout = QVBoxLayout(self.initiative_content)
        self.initiative_layout.setContentsMargins(0, 0, 0, 0)
        self.initiative_layout.setSpacing(4)
        self.initiative_scroll.setWidget(self.initiative_content)
        initiative_layout.addWidget(self.initiative_scroll, stretch=1)
        battlefield_layout.addWidget(self.initiative_rail)
        battlefield_layout.addWidget(self.battlefield_widget, stretch=1)

        encounter_layout.addWidget(battlefield_area, stretch=1)

        self.victory_overlay = QFrame(self.encounter_panel)
        self.victory_overlay.setObjectName("victoryOverlay")
        self.victory_overlay.setStyleSheet(
            "QFrame { background: rgba(12, 10, 6, 190); }"
            "QLabel { color: #f6edd9; }"
            "QPushButton { min-width: 140px; min-height: 40px; }"
        )
        self.victory_overlay.hide()
        overlay_layout = QVBoxLayout(self.victory_overlay)
        overlay_layout.setContentsMargins(40, 40, 40, 40)
        overlay_layout.setSpacing(12)
        overlay_layout.addStretch(1)
        overlay_card = QFrame()
        overlay_card.setObjectName("overlayCard")
        overlay_card.setStyleSheet(
            "QFrame { background: #1d1710; border: 2px solid #c9a227; border-radius: 10px; }"
        )
        overlay_card_layout = QVBoxLayout(overlay_card)
        overlay_card_layout.setContentsMargins(24, 24, 24, 24)
        overlay_card_layout.setSpacing(12)
        overlay_title = QLabel("Victory")
        overlay_title.setObjectName("overlayTitle")
        overlay_title_font = QFont()
        overlay_title_font.setPointSize(18)
        overlay_title_font.setBold(True)
        overlay_title.setFont(overlay_title_font)
        overlay_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_card_layout.addWidget(overlay_title)
        self.victory_overlay_message = QLabel("")
        self.victory_overlay_message.setWordWrap(True)
        self.victory_overlay_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_card_layout.addWidget(self.victory_overlay_message)
        self.victory_overlay_button = QPushButton("Continue")
        self.victory_overlay_button.clicked.connect(self._continue_pending_transition)
        overlay_card_layout.addWidget(
            self.victory_overlay_button, alignment=Qt.AlignmentFlag.AlignCenter
        )
        overlay_layout.addWidget(overlay_card, alignment=Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addStretch(1)

        layout.addWidget(self.scene_group, stretch=1)
        layout.addWidget(self.story_choices_group, stretch=1)
        layout.addWidget(self.encounter_panel, stretch=2)
        return container

    def _set_team_outlines_visible(self, visible: bool) -> None:
        self._show_team_outlines = visible
        self.battlefield_widget.set_team_outlines_visible(visible)
        self.sidebar.set_team_outlines_checked(visible)

    def _set_always_show_creature_names(self, visible: bool) -> None:
        self._always_show_creature_names = visible
        self.battlefield_widget.set_always_show_creature_names(visible)
        self.sidebar.set_creature_names_checked(visible)

    def _build_group(self, title: str) -> QFrame:
        group = QFrame()
        group.setObjectName("panel")
        group.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        return group

    def _wrap_in_scroll(self, content_layout: QVBoxLayout) -> QScrollArea:
        container = QWidget()
        container.setLayout(content_layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(container)
        return scroll

    def _build_readonly_text(
        self,
        minimum_height: int = 100,
        maximum_height: int | None = None,
    ) -> QTextEdit:
        text = QTextEdit()
        text.setReadOnly(True)
        text.setMinimumHeight(minimum_height)
        if maximum_height is not None:
            text.setMaximumHeight(maximum_height)
        return text

    def refresh_view(self) -> None:
        presentation = self._build_session_presentation()
        self._presentation = presentation
        assert self._observation is not None
        self.sidebar.sync(self._observation)
        if presentation.encounter is None:
            self._pending_target_mode = None
            self._action_menu_scope = None

        self.scene_text.setPlainText(presentation.story_text or "")

        if presentation.encounter is None:
            self.sidebar.leave_encounter()
            self.scene_group.show()
            self.story_choices_group.show()
            self.encounter_panel.hide()
            self.victory_overlay.hide()
            self.battlefield_widget.set_area_overlay(None)
            self._render_story_actions(presentation.story_actions)
        else:
            self.sidebar.enter_encounter()
            self.scene_group.hide()
            self.story_choices_group.hide()
            self.encounter_panel.show()
            assert self._observation is not None
            assert self._observation.encounter is not None
            self._sync_combat_log_round(self._observation.encounter)
            self._render_encounter(presentation)
        self._sync_victory_overlay(presentation)
        self._schedule_ai_step_if_needed()

    def _render_story_actions(self, actions: list[ActionObservation]) -> None:
        clear_layout(self.story_choices_layout)
        for action in actions:
            button = QPushButton(action.label)
            button.clicked.connect(
                lambda _checked=False, action_id=action.id: self._select_action(
                    action_id
                )
            )
            self.story_choices_layout.addWidget(button)
        self.story_choices_layout.addStretch(1)

    def _render_encounter(self, presentation: SessionPresentation) -> None:
        encounter = presentation.encounter
        assert encounter is not None
        self.battlefield_widget.set_battlefield(encounter.battlefield)
        if not movement_plan_is_current(
            self._movement_plan,
            encounter.battlefield,
        ):
            self._clear_movement_plan()

        target_modes = selection_modes(encounter.non_movement_actions)
        if not mode_is_available(
            encounter.non_movement_actions,
            target_modes,
            self._pending_target_mode,
        ):
            self._pending_target_mode = None
        self.battlefield_widget.set_cell_targeting_enabled(
            pending_area_action(
                encounter.non_movement_actions,
                self._pending_target_mode,
            )
            is not None
        )
        self.battlefield_widget.set_area_overlay(
            pending_area_overlay(
                encounter.non_movement_actions,
                self._pending_target_mode,
            )
        )
        selected_targetable_actions = (
            target_modes.get(self._pending_target_mode, {})
            if self._pending_target_mode is not None
            else {}
        )
        targetable_refs = {
            target_ref
            for action in selected_targetable_actions.values()
            if action.enabled
            if (target_ref := target_creature_ref(action)) is not None
        }
        observation = self._observation or self.game.observe()
        target_allocations = allocation_counts(observation)
        targeting_status = allocation_status(observation)
        self.battlefield_widget.set_targeting_state(
            targetable_refs,
            allocation_counts=target_allocations,
            targeting_label=targeting_status,
        )

        self._action_menu_scope = self._encounter_panel_renderer.render(
            encounter,
            observation,
            pending_target_mode=self._pending_target_mode,
            action_menu_scope=self._action_menu_scope,
        )

    def _sync_victory_overlay(self, presentation: SessionPresentation) -> None:
        encounter = presentation.encounter
        if encounter is None or encounter.transition_message is None:
            self.victory_overlay.hide()
            return
        self.victory_overlay_message.setText(encounter.transition_message)
        self.victory_overlay_button.setEnabled(encounter.transition_action is not None)
        self._update_victory_overlay_geometry()
        self.victory_overlay.show()
        self.victory_overlay.raise_()

    def _update_victory_overlay_geometry(self) -> None:
        if not hasattr(self, "victory_overlay"):
            return
        self.victory_overlay.setGeometry(self.encounter_panel.rect())

    def _continue_pending_transition(self) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        action = self._presentation.encounter.transition_action
        if action is not None:
            self._select_action(action.id)

    def _open_action_menu(self, economy: str, bucket: str) -> None:
        self._clear_movement_plan()
        self._pending_target_mode = None
        self._action_menu_scope = ActionMenuScope(economy=economy, bucket=bucket)
        self.refresh_view()

    def _close_action_menu(self, scope: ActionMenuScope | None = None) -> None:
        self._clear_movement_plan()
        self._pending_target_mode = None
        if scope is not None and self._action_menu_scope != scope:
            return
        self._action_menu_scope = None
        self.refresh_view()

    def _end_turn(self) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        self._pending_target_mode = None
        self._action_menu_scope = None
        action = self._presentation.encounter.end_turn_action
        if action is not None:
            self._select_action(action.id)

    def _select_action(self, action_id: str) -> None:
        self._clear_movement_plan()
        previous_scope = self._action_menu_scope
        selected_action = (
            next(
                (
                    action
                    for action in self._presentation.encounter.non_movement_actions
                    if action.id == action_id
                ),
                None,
            )
            if self._presentation is not None
            and self._presentation.encounter is not None
            else None
        )
        self._pending_target_mode = None
        self._action_menu_scope = None
        command_result = self.game.execute(
            SelectAction(
                action_id=action_id,
                expected_decision_id=self._current_decision_id(),
            )
        )
        result = self._accepted_update(command_result)
        if result is None:
            return
        completed_allocation = completed_allocation_action(result.observation)
        if completed_allocation is not None:
            confirmation = self.game.execute(
                ConfirmTargeting(
                    expected_decision_id=self._required_decision_id(),
                )
            )
            confirmed = self._accepted_update(confirmation)
            if confirmed is not None:
                result = confirmed
        if (
            selected_action is not None
            and selected_action.kind == "toggle_spell_target"
        ):
            if completed_allocation is None:
                self._pending_target_mode = mode_for_action(selected_action)
        elif (
            selected_action is not None
            and selected_action.kind == "spell"
            and result.observation.encounter is not None
            and result.observation.encounter.decision.kind == "spell_targets"
        ):
            self._pending_target_mode = TargetSelectionMode(
                kind="toggle_spell_target",
                source_trigger_id=selected_action.source_id,
            )
        if (
            result.observation.encounter is not None
            and result.observation.encounter.decision.kind == "spell_targets"
        ):
            self._action_menu_scope = previous_scope
        self._apply_turn_result(
            result,
            follow_up_attack_mode=(
                mode_for_action(selected_action)
                if selected_action is not None and selected_action.kind == "attack"
                else None
            ),
        )

    def _select_action_by_id(self, action_id: str) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        action = next(
            (
                action
                for action in self._presentation.encounter.non_movement_actions
                if action.id == action_id
            ),
            None,
        )
        if action is not None:
            self._select_action(action.id)

    def _toggle_target_action(self, mode: TargetSelectionMode) -> None:
        self._clear_movement_plan()
        self._pending_target_mode = None if self._pending_target_mode == mode else mode
        self.refresh_view()

    def _handle_battlefield_creature_clicked(
        self,
        creature_ref: str,
        remove_allocation: bool = False,
    ) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        if self._pending_target_mode is None:
            self._begin_movement_plan(creature_ref)
            return
        action = action_for_target_click(
            self._presentation.encounter.non_movement_actions,
            self._pending_target_mode,
            creature_ref,
            remove_allocation=remove_allocation,
        )
        if action is None:
            # Follow-up attack targeting remains active while a Multiattack has
            # attacks left. Let the actor's own token reopen movement planning
            # between those attacks; _begin_movement_plan rejects non-active
            # creatures and actors without legal movement.
            self._begin_movement_plan(creature_ref)
            return
        if not action.enabled:
            return
        if action.kind == "toggle_spell_target":
            result = self.game.execute(
                ChangeTarget(
                    target_ref=creature_ref,
                    remove=remove_allocation,
                    expected_decision_id=self._required_decision_id(),
                    source_trigger_id=action.source_trigger_id,
                )
            )
            update = self._accepted_update(result)
            if update is not None:
                completed = completed_allocation_action(update.observation)
                if completed is not None:
                    confirmed = self._accepted_update(
                        self.game.execute(
                            ConfirmTargeting(
                                expected_decision_id=self._required_decision_id()
                            )
                        )
                    )
                    if confirmed is not None:
                        update = confirmed
                self._apply_turn_result(update)
            return
        self._select_action(action.id)

    def _handle_battlefield_cell_clicked(self, x: int, y: int) -> None:
        path = (
            self._movement_plan.path_to((x, y))
            if self._movement_plan is not None
            else None
        )
        if path:
            self._confirm_movement_path(path)
            return
        self._handle_battlefield_point_clicked(x + 0.5, y + 0.5)

    def _begin_movement_plan(self, creature_ref: str) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        encounter = self._presentation.encounter
        plan = build_movement_plan(encounter, creature_ref)
        if plan is None:
            return
        self._movement_plan = plan
        self._pending_target_mode = None
        self._action_menu_scope = None
        self.battlefield_widget.set_movement_plan(plan)

    def _confirm_movement_path(self, path: tuple[str, ...]) -> None:
        plan = self._movement_plan
        self._clear_movement_plan()
        if plan is None:
            return
        for direction in path:
            presentation = self._build_session_presentation()
            encounter = presentation.encounter
            if encounter is None:
                break
            action = encounter.movement_actions.get(direction)
            if action is None or action.creature_ref != plan.creature_ref:
                break
            result = self.game.execute(
                SelectAction(
                    action_id=action.id,
                    expected_decision_id=self._current_decision_id(),
                )
            )
            update = self._accepted_update(result)
            if update is None:
                break
            self._apply_turn_result(update)

    def _clear_movement_plan(self) -> None:
        self._movement_plan = None
        if hasattr(self, "battlefield_widget"):
            self.battlefield_widget.set_movement_plan(None)

    def _cancel_battlefield_interaction(self) -> None:
        self._clear_movement_plan()
        if self._presentation is not None and self._presentation.encounter is not None:
            cancel = cancel_targeting_action(
                self._presentation.encounter.non_movement_actions
            )
            if cancel is not None:
                result = self.game.execute(
                    CancelTargeting(expected_decision_id=self._required_decision_id())
                )
                update = self._accepted_update(result)
                if update is not None:
                    self._apply_turn_result(update)
                return
        self._pending_target_mode = None
        self.refresh_view()

    def _set_spell_resource_allocation(self, target_ref: str, amount: int) -> None:
        decision_id = self._current_decision_id()
        if decision_id is None:
            return
        result = self.game.execute(
            SetResourceAllocation(
                target_ref=target_ref,
                amount=amount,
                expected_decision_id=decision_id,
            )
        )
        update = self._accepted_update(result)
        if update is not None:
            self._apply_turn_result(update)

    def _handle_battlefield_point_clicked(self, x: float, y: float) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        action = pending_area_action(
            self._presentation.encounter.non_movement_actions,
            self._pending_target_mode,
        )
        if action is None:
            return
        decision_id = self._current_decision_id()
        if decision_id is None:
            return
        self._pending_target_mode = None
        self._action_menu_scope = None
        result = self.game.execute(
            AimAction(
                action_id=action.id,
                x=x,
                y=y,
                expected_decision_id=decision_id,
            )
        )
        update = self._accepted_update(result)
        if update is not None:
            self._apply_turn_result(update)

    def _apply_turn_result(
        self,
        result: GameUpdate,
        *,
        follow_up_attack_mode: TargetSelectionMode | None = None,
    ) -> None:
        encounter = result.observation.encounter
        was_in_encounter = (
            self._presentation is not None and self._presentation.encounter is not None
        )
        is_combat_result = was_in_encounter or encounter is not None
        if encounter is not None:
            self._sync_combat_log_round(encounter)
        if is_combat_result:
            roll_views = build_roll_views(list(result.events))
            messages = without_roll_details(list(result.messages))
            self.sidebar.append_combat_log(messages, roll_views)
            if messages or roll_views:
                QTimer.singleShot(20, self._scroll_roll_log_to_bottom)

        if result.should_exit:
            self.close()
            return
        if follow_up_attack_mode is not None:
            self._pending_target_mode = self._available_follow_up_attack_mode(
                follow_up_attack_mode
            )
        self.refresh_view()

    def _available_follow_up_attack_mode(
        self,
        attack_mode: TargetSelectionMode,
    ) -> TargetSelectionMode | None:
        presentation = self._build_session_presentation()
        encounter = presentation.encounter
        if encounter is None or encounter.resources.attacks_available <= 0:
            return None
        target_modes = selection_modes(encounter.non_movement_actions)
        return attack_mode if target_modes.get(attack_mode) else None

    def _build_session_presentation(self) -> SessionPresentation:
        observation = self.game.observe()
        self._observation = observation
        config = getattr(self, "_encounter_presentation_config", None)
        if config is None:
            return build_session_presentation(observation)
        return build_session_presentation(observation, config=config)

    def _accepted_update(self, result: CommandResult) -> GameUpdate | None:
        if result.update is None:
            self._clear_movement_plan()
            self._pending_target_mode = None
            self.refresh_view()
            return None
        self._observation = result.update.observation
        return result.update

    def _current_decision_id(self) -> str | None:
        observation = self._observation or self.game.observe()
        return (
            observation.encounter.decision.id
            if observation.encounter is not None
            else None
        )

    def _required_decision_id(self) -> str:
        decision_id = self._current_decision_id()
        if decision_id is None:
            raise RuntimeError("No encounter decision is active.")
        return decision_id

    def _sync_combat_log_round(self, encounter: EncounterObservation) -> None:
        entering_encounter = self._combat_log_scene_id != encounter.encounter_id
        if entering_encounter:
            self.sidebar.clear_combat_log()
            self._combat_log_scene_id = encounter.encounter_id
            self._logged_round_number = None
        if self._logged_round_number == encounter.round_number:
            return
        self.sidebar.start_round(encounter.round_number)
        self._logged_round_number = encounter.round_number
        if entering_encounter:
            creature_ref = encounter.decision.creature_ref
            self.sidebar.start_turn(
                f"{encounter.creature(creature_ref).name}'s turn"
            )
        QTimer.singleShot(20, self._scroll_roll_log_to_bottom)

    def _scroll_roll_log_to_bottom(self) -> None:
        self.sidebar.scroll_combat_log_to_bottom()

    def _schedule_ai_step_if_needed(self) -> None:
        observation = self._observation or self.game.observe()
        if (
            self._automatic_step_scheduled
            or observation.encounter is None
            or observation.transition is not None
            or not observation.requires_automatic_advance
        ):
            return
        self._automatic_step_scheduled = True
        QTimer.singleShot(500, self._advance_automatic_step)

    def _advance_automatic_step(self) -> None:
        self._automatic_step_scheduled = False
        observation = self.game.observe()
        self._observation = observation
        if (
            observation.encounter is None
            or not observation.requires_automatic_advance
        ):
            return
        self._apply_turn_result(self.game.advance_automatic())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_victory_overlay_geometry()
