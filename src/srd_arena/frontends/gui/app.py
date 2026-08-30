"""Coordinate the PySide window with frontend-neutral engine updates."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QWidget

from srd_arena.engine.api import (
    EncounterObservation,
    GameUpdate,
)
from srd_arena.scenarios.api import ScenarioPresentation

from .presentation.dice import build_roll_views, without_roll_details
from .presentation.models import SessionPresentation
from .presentation.session import build_session_presentation
from .presenter import GamePresenter
from .ui.encounter import (
    ActionMenuScope,
    TargetSelectionMode,
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
    mode_for_action,
    mode_is_available,
    pending_area_action,
    pending_area_overlay,
    selection_modes,
    target_creature_ref,
)
from .ui.game_surface import GameSurface, GameSurfaceCallbacks
from .ui.sidebar import GameSidebar, SidebarCallbacks

AUTOMATIC_ACTION_DELAY_MS = 500


class GameWindow(QMainWindow):
    """Render a running game and translate Qt interactions into app commands.

    The window owns widget state only. Combat decisions and validation pass
    through the engine boundary rather than being implemented here.
    """

    def __init__(
        self,
        presenter: GamePresenter,
        *,
        image_root: Path | None = None,
        presentation_config: ScenarioPresentation | None = None,
        show_encounter_json: bool = False,
        pause_between_automatic_actions: bool = True,
    ):
        super().__init__()
        self.presenter = presenter
        self._encounter_presentation_config = (
            presentation_config or ScenarioPresentation()
        )
        self._presentation: SessionPresentation | None = None
        self._action_menu_scope: ActionMenuScope | None = None
        self._combat_log_scene_id: str | None = None
        self._logged_round_number: int | None = None
        self._automatic_step_scheduled = False
        self._pause_between_automatic_actions = pause_between_automatic_actions
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

        self.surface = GameSurface(
            GameSurfaceCallbacks(
                select_story_action=self._select_action,
                creature_clicked=self._handle_battlefield_creature_clicked,
                cell_clicked=self._handle_battlefield_cell_clicked,
                point_clicked=self._handle_battlefield_point_clicked,
                interaction_cancelled=self._cancel_battlefield_interaction,
                continue_transition=self._continue_pending_transition,
            ),
            image_root=image_root,
        )
        root_layout.addWidget(self.surface, stretch=1)
        self.sidebar = GameSidebar(
            SidebarCallbacks(
                select_log_action=self._select_action_by_id,
                end_turn=self._end_turn,
                close_window=self._close_window,
                set_team_outlines_visible=self._set_team_outlines_visible,
                set_creature_names_visible=self._set_always_show_creature_names,
            ),
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

    def _close_window(self) -> None:
        self.close()

    def _set_team_outlines_visible(self, visible: bool) -> None:
        self._show_team_outlines = visible
        self.surface.battlefield.set_team_outlines_visible(visible)
        self.sidebar.set_team_outlines_checked(visible)

    def _set_always_show_creature_names(self, visible: bool) -> None:
        self._always_show_creature_names = visible
        self.surface.battlefield.set_always_show_creature_names(visible)
        self.sidebar.set_creature_names_checked(visible)

    def refresh_view(self) -> None:
        presentation = self._build_session_presentation()
        self._presentation = presentation
        observation = self.presenter.observation
        self.sidebar.sync(observation)
        if presentation.encounter is None:
            self.presenter.clear_target_mode()
            self._action_menu_scope = None

        if presentation.encounter is None:
            self.sidebar.leave_encounter()
            self.surface.show_story(
                presentation.story_text,
                presentation.story_actions,
            )
        else:
            self.sidebar.enter_encounter()
            self.surface.show_encounter()
            assert observation.encounter is not None
            self._sync_combat_log_round(observation.encounter)
            self._render_encounter(presentation)
        encounter = presentation.encounter
        self.surface.sync_victory_overlay(
            encounter.transition_message if encounter is not None else None,
            can_continue=(
                encounter is not None and encounter.transition_action is not None
            ),
        )
        self._schedule_ai_step_if_needed()

    def _render_encounter(self, presentation: SessionPresentation) -> None:
        encounter = presentation.encounter
        assert encounter is not None
        battlefield = self.surface.battlefield
        battlefield.set_battlefield(encounter.battlefield)
        self.surface.render_initiative(encounter.resources.initiative)
        if not movement_plan_is_current(
            self._movement_plan,
            encounter.battlefield,
        ):
            self._clear_movement_plan()

        target_modes = selection_modes(encounter.non_movement_actions)
        pending_target_mode = self.presenter.pending_target_mode
        if not mode_is_available(
            encounter.non_movement_actions,
            target_modes,
            pending_target_mode,
        ):
            self.presenter.clear_target_mode()
            pending_target_mode = None
        battlefield.set_cell_targeting_enabled(
            pending_area_action(
                encounter.non_movement_actions,
                pending_target_mode,
            )
            is not None
        )
        battlefield.set_area_overlay(
            pending_area_overlay(
                encounter.non_movement_actions,
                pending_target_mode,
            )
        )
        selected_targetable_actions = (
            target_modes.get(pending_target_mode, {})
            if pending_target_mode is not None
            else {}
        )
        targetable_refs = {
            target_ref
            for action in selected_targetable_actions.values()
            if action.enabled
            if (target_ref := target_creature_ref(action)) is not None
        }
        observation = self.presenter.observation
        target_allocations = allocation_counts(observation)
        targeting_status = allocation_status(observation)
        battlefield.set_targeting_state(
            targetable_refs,
            allocation_counts=target_allocations,
            targeting_label=targeting_status,
        )

        self._action_menu_scope = self._encounter_panel_renderer.render(
            encounter,
            observation,
            pending_target_mode=pending_target_mode,
            action_menu_scope=self._action_menu_scope,
        )

    def _continue_pending_transition(self) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        action = self._presentation.encounter.transition_action
        if action is not None:
            self._select_action(action.id)

    def _open_action_menu(self, economy: str, bucket: str) -> None:
        self._clear_movement_plan()
        self.presenter.clear_target_mode()
        self._action_menu_scope = ActionMenuScope(economy=economy, bucket=bucket)
        self.refresh_view()

    def _close_action_menu(self, scope: ActionMenuScope | None = None) -> None:
        self._clear_movement_plan()
        self.presenter.clear_target_mode()
        if scope is not None and self._action_menu_scope != scope:
            return
        self._action_menu_scope = None
        self.refresh_view()

    def _end_turn(self) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        self.presenter.clear_target_mode()
        self._action_menu_scope = None
        action = self._presentation.encounter.end_turn_action
        if action is not None:
            self._select_action(action.id)

    def _select_action(self, action_id: str) -> None:
        self._clear_movement_plan()
        previous_scope = self._action_menu_scope
        self._action_menu_scope = None
        selection = self.presenter.select_action(action_id)
        result = self._handle_command_update(
            selection.update if selection is not None else None
        )
        if result is None:
            return
        assert selection is not None
        selected_action = selection.selected_action
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
        self.presenter.toggle_target_mode(mode)
        self.refresh_view()

    def _handle_battlefield_creature_clicked(
        self,
        creature_ref: str,
        remove_allocation: bool = False,
    ) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        pending_target_mode = self.presenter.pending_target_mode
        if pending_target_mode is None:
            self._begin_movement_plan(creature_ref)
            return
        action = action_for_target_click(
            self._presentation.encounter.non_movement_actions,
            pending_target_mode,
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
            update = self._handle_command_update(
                self.presenter.change_target(
                    creature_ref,
                    remove=remove_allocation,
                    source_trigger_id=action.source_trigger_id,
                )
            )
            if update is not None:
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
        self.presenter.clear_target_mode()
        self._action_menu_scope = None
        self.surface.battlefield.set_movement_plan(plan)

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
            selection = self.presenter.select_action(action.id)
            update = self._handle_command_update(
                selection.update if selection is not None else None
            )
            if update is None:
                break
            self._apply_turn_result(update)

    def _clear_movement_plan(self) -> None:
        self._movement_plan = None
        if hasattr(self, "surface"):
            self.surface.battlefield.set_movement_plan(None)

    def _cancel_battlefield_interaction(self) -> None:
        self._clear_movement_plan()
        if self._presentation is not None and self._presentation.encounter is not None:
            cancel = cancel_targeting_action(
                self._presentation.encounter.non_movement_actions
            )
            if cancel is not None:
                update = self._handle_command_update(self.presenter.cancel_targeting())
                if update is not None:
                    self._apply_turn_result(update)
                return
        self.presenter.clear_target_mode()
        self.refresh_view()

    def _set_spell_resource_allocation(self, target_ref: str, amount: int) -> None:
        update = self._handle_command_update(
            self.presenter.set_resource_allocation(target_ref, amount)
        )
        if update is not None:
            self._apply_turn_result(update)

    def _handle_battlefield_point_clicked(self, x: float, y: float) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        action = pending_area_action(
            self._presentation.encounter.non_movement_actions,
            self.presenter.pending_target_mode,
        )
        if action is None:
            return
        self._action_menu_scope = None
        update = self._handle_command_update(self.presenter.aim_action(action.id, x, y))
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
            self.presenter.set_target_mode(
                self._available_follow_up_attack_mode(follow_up_attack_mode)
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
        observation = self.presenter.observation
        config = getattr(self, "_encounter_presentation_config", None)
        if config is None:
            return build_session_presentation(observation)
        return build_session_presentation(observation, config=config)

    def _handle_command_update(self, update: GameUpdate | None) -> GameUpdate | None:
        if update is None:
            self._clear_movement_plan()
            self.presenter.clear_target_mode()
            self.refresh_view()
            return None
        return update

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
            self.sidebar.start_turn(f"{encounter.creature(creature_ref).name}'s turn")
        QTimer.singleShot(20, self._scroll_roll_log_to_bottom)

    def _scroll_roll_log_to_bottom(self) -> None:
        self.sidebar.scroll_combat_log_to_bottom()

    def _schedule_ai_step_if_needed(self) -> None:
        observation = self.presenter.observation
        if (
            self._automatic_step_scheduled
            or observation.encounter is None
            or observation.transition is not None
            or not observation.requires_automatic_advance
        ):
            return
        self._automatic_step_scheduled = True
        delay_ms = (
            AUTOMATIC_ACTION_DELAY_MS if self._pause_between_automatic_actions else 0
        )
        QTimer.singleShot(delay_ms, self._advance_automatic_step)

    def _advance_automatic_step(self) -> None:
        self._automatic_step_scheduled = False
        observation = self.presenter.refresh()
        if observation.encounter is None or not observation.requires_automatic_advance:
            return
        update = (
            self.presenter.advance_one_automatic_action()
            if self._pause_between_automatic_actions
            else self.presenter.advance_until_input_required()
        )
        self._apply_turn_result(update)
