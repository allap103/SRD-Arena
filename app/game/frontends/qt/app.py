from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from ...combat.models import ActionCost, EncounterAction
from ...combat.geometry import (
    Vector2D,
    build_directional_area,
    build_radius_area,
    serialize_area,
)
from ...combat.spells import (
    parse_spell_action_value,
    spell_action_value,
    spell_range_squares,
)
from ...runtime.game import GAME_DIR, Game
from ...presentation.dice import build_roll_views, without_roll_details
from ...presentation.session import (
    MOVE_DIRECTIONS,
    SessionPresentation,
    build_session_presentation,
)
from ...models.scene import Grid, Position
from ...presentation.models import ActionView
from ...runtime.session import (
    EXIT_CHOICE_TEXT,
    LOAD_CHOICE_TEXT,
    LONG_REST_CHOICE_TEXT,
    SAVE_CHOICE_TEXT,
    SHORT_REST_CHOICE_TEXT,
    GameSession,
)
from ...support.scenarios import ScenarioInfo, list_scenarios
from .theme import apply_fantasy_theme
from .ui.encounter import (
    ARROW_LABELS,
    ENCOUNTER_BUTTON_HEIGHT,
    RESOURCE_BAR_HEIGHT,
    ActionMenuScope,
    BattlefieldWidget,
    DiceRollPanel,
    TargetSelectionMode,
    clear_layout,
    spell_slot_rich_text,
)

try:
    from PySide6.QtCore import QSize, Qt, QTimer, Signal
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QFileDialog,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QStackedWidget,
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
    QFileDialog = object  # type: ignore[assignment]
    QGridLayout = object  # type: ignore[assignment]
    QHBoxLayout = object  # type: ignore[assignment]
    QLabel = object  # type: ignore[assignment]
    QMainWindow = object  # type: ignore[assignment]
    QMessageBox = object  # type: ignore[assignment]
    QPushButton = object  # type: ignore[assignment]
    QScrollArea = object  # type: ignore[assignment]
    QSizePolicy = object  # type: ignore[assignment]
    QStackedWidget = object  # type: ignore[assignment]
    QTextEdit = object  # type: ignore[assignment]
    QVBoxLayout = object  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]
SIDEBAR_WIDTH = 220


def _require_pyside6() -> None:
    if QApplication is None:
        raise RuntimeError(
            "PySide6 is not installed. Install project dependencies including PySide6 to use this frontend."
        )


class CyoaPySide6Window(QMainWindow):
    def __init__(
        self,
        game: Game | None = None,
        *,
        show_encounter_json: bool = False,
    ):
        _require_pyside6()
        super().__init__()
        self.game = game or Game(GAME_DIR)
        self.session: GameSession = self.game.create_session()
        self.session.ai_action_limit = 1
        self._items_by_id = {item.id: item for item in self.game.items}
        self._presentation: SessionPresentation | None = None
        self._pending_target_mode: TargetSelectionMode | None = None
        self._action_menu_scope: ActionMenuScope | None = None
        self._combat_log_scene_id: str | None = None
        self._logged_round_number: int | None = None
        self._ai_step_scheduled = False
        self._show_encounter_json = show_encounter_json

        self.setWindowTitle("CYOA")
        self.resize(1400, 900)

        central = QWidget()
        central.setObjectName("rootCentral")
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._build_main_content(), stretch=1)
        root_layout.addWidget(self._build_sidebar())

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

        self.battlefield_widget = BattlefieldWidget(self.game.directory)
        self.battlefield_widget.setObjectName("combatBoard")
        self.battlefield_widget.actor_clicked.connect(self._handle_battlefield_actor_clicked)
        self.battlefield_widget.cell_clicked.connect(self._handle_battlefield_cell_clicked)
        self.battlefield_widget.point_clicked.connect(self._handle_battlefield_point_clicked)
        battlefield_layout.addWidget(self.battlefield_widget, stretch=1)

        self.initiative_rail = QFrame()
        self.initiative_rail.setObjectName("rollRail")
        self.initiative_rail.setFrameShape(QFrame.Shape.StyledPanel)
        self.initiative_rail.setFixedWidth(220)
        initiative_layout = QVBoxLayout(self.initiative_rail)
        initiative_layout.setContentsMargins(10, 10, 10, 10)
        initiative_layout.setSpacing(8)
        initiative_title = QLabel("Initiative")
        initiative_title.setObjectName("sectionTitle")
        initiative_title.setStyleSheet("QLabel { font-weight: 700; }")
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

        roll_rail = QFrame()
        roll_rail.setObjectName("rollRail")
        roll_rail.setFrameShape(QFrame.Shape.StyledPanel)
        roll_rail.setFixedWidth(310)
        roll_rail_layout = QVBoxLayout(roll_rail)
        roll_rail_layout.setContentsMargins(10, 10, 10, 10)
        roll_rail_layout.setSpacing(8)
        roll_title = QLabel("Combat Log")
        roll_title.setObjectName("sectionTitle")
        roll_title.setStyleSheet("QLabel { font-weight: 700; }")
        roll_rail_layout.addWidget(roll_title)

        self.dice_roll_panel = DiceRollPanel(self._select_action_by_id)
        self.roll_scroll = QScrollArea()
        self.roll_scroll.setWidgetResizable(True)
        self.roll_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.roll_scroll.setWidget(self.dice_roll_panel)
        roll_rail_layout.addWidget(self.roll_scroll, stretch=1)
        battlefield_layout.addWidget(roll_rail)

        encounter_layout.addWidget(battlefield_area, stretch=1)

        encounter_controls = QWidget()
        encounter_controls.setFixedHeight(280)
        encounter_controls.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        encounter_controls_layout = QHBoxLayout(encounter_controls)
        encounter_controls_layout.setContentsMargins(0, 0, 0, 0)
        encounter_controls_layout.setSpacing(10)

        self.movement_group = QWidget()
        self.movement_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        movement_layout = QVBoxLayout(self.movement_group)
        movement_layout.setContentsMargins(0, 0, 0, 0)
        movement_layout.setSpacing(8)
        movement_layout.addWidget(
            self._build_action_header("Movement", True, "#2f6f9d", show_indicator=False)
        )
        self.movement_buttons: dict[str, QPushButton] = {}
        movement_grid = QGridLayout()
        movement_grid.setSpacing(6)
        positions = {
            "up-left": (0, 0),
            "up": (0, 1),
            "up-right": (0, 2),
            "left": (1, 0),
            "right": (1, 2),
            "down-left": (2, 0),
            "down": (2, 1),
            "down-right": (2, 2),
        }
        self.movement_status = QWidget()
        self.movement_status_layout = QVBoxLayout(self.movement_status)
        self.movement_status_layout.setContentsMargins(0, 0, 0, 0)
        self.movement_status_layout.setSpacing(6)
        movement_layout.addWidget(self.movement_status)
        for direction in MOVE_DIRECTIONS:
            button = QPushButton(ARROW_LABELS[direction])
            button.setObjectName("movementButton")
            button.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
            button.clicked.connect(
                lambda _checked=False, move_direction=direction: self._trigger_move(move_direction)
            )
            self.movement_buttons[direction] = button
            row, col = positions[direction]
            movement_grid.addWidget(button, row, col)
        movement_center = QLabel("Move")
        movement_center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        movement_grid.addWidget(movement_center, 1, 1)
        movement_layout.addLayout(movement_grid)
        movement_layout.addStretch(1)
        self.movement_group.setFixedWidth(210)

        self.encounter_actions_group = self._build_untitled_panel()
        self.encounter_actions_layout = QHBoxLayout()
        self.encounter_actions_layout.setSpacing(12)
        self.encounter_actions_group.layout().addWidget(
            self._wrap_in_scroll(self.encounter_actions_layout)
        )
        actions_footer = QWidget()
        actions_footer_layout = QHBoxLayout(actions_footer)
        actions_footer_layout.setContentsMargins(0, 0, 0, 0)
        actions_footer_layout.addStretch(1)
        self.end_turn_button = QPushButton("End Turn")
        self.end_turn_button.setObjectName("endTurnButton")
        self.end_turn_button.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
        self.end_turn_button.clicked.connect(self._end_turn)
        actions_footer_layout.addWidget(self.end_turn_button)
        self.encounter_actions_group.layout().addWidget(actions_footer)
        encounter_controls_layout.addWidget(self.encounter_actions_group, stretch=1)

        encounter_layout.addWidget(encounter_controls)

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
        overlay_card_layout.addWidget(self.victory_overlay_button, alignment=Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(overlay_card, alignment=Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addStretch(1)

        layout.addWidget(self.scene_group, stretch=1)
        layout.addWidget(self.story_choices_group, stretch=1)
        layout.addWidget(self.encounter_panel, stretch=2)
        return container

    def _build_sidebar(self) -> QWidget:
        sidebar = self._framed_panel("Menu")
        sidebar.setObjectName("sidebarPanel")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = sidebar.layout()

        self.sidebar_stack = QStackedWidget()
        self.sidebar_stack.addWidget(self._build_sidebar_root())
        self.sidebar_stack.addWidget(self._build_inventory_page())
        self.sidebar_stack.addWidget(self._build_attributes_page())
        self.sidebar_stack.addWidget(self._build_system_page())
        if self._show_encounter_json:
            self.sidebar_stack.addWidget(self._build_encounter_json_page())
        layout.addWidget(self.sidebar_stack)
        return sidebar

    def _build_sidebar_root(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._sidebar_button("Attributes", self.show_attributes))
        layout.addWidget(self._sidebar_button("Inventory", self.show_inventory))
        layout.addWidget(self._sidebar_button("System", self.show_system_menu))
        layout.addStretch(1)
        self.short_rest_button = self._sidebar_button(
            SHORT_REST_CHOICE_TEXT,
            lambda: self._trigger_rest("system_short_rest"),
        )
        self.long_rest_button = self._sidebar_button(
            LONG_REST_CHOICE_TEXT,
            lambda: self._trigger_rest("system_long_rest"),
        )
        layout.addWidget(self.short_rest_button)
        layout.addWidget(self.long_rest_button)
        return page

    def _build_inventory_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._sidebar_button("Back", self.show_menu_root))
        self.inventory_text = self._build_readonly_text(minimum_height=400)
        layout.addWidget(self.inventory_text, stretch=1)
        return page

    def _build_attributes_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._sidebar_button("Back", self.show_menu_root))
        self.attributes_text = self._build_readonly_text(minimum_height=400)
        layout.addWidget(self.attributes_text, stretch=1)
        return page

    def _build_system_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._sidebar_button("Back", self.show_menu_root))
        layout.addWidget(self._sidebar_button(SAVE_CHOICE_TEXT, self._system_save))
        layout.addWidget(self._sidebar_button(LOAD_CHOICE_TEXT, self._system_load))
        if self._show_encounter_json:
            layout.addWidget(
                self._sidebar_button("Encounter JSON", self.show_encounter_json)
            )
        layout.addWidget(self._sidebar_button(EXIT_CHOICE_TEXT, self.close))
        layout.addStretch(1)
        return page

    def _build_encounter_json_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._sidebar_button("Back", self.show_system_menu))
        self.encounter_json_status = QLabel("Waiting for encounter data.")
        self.encounter_json_status.setWordWrap(True)
        layout.addWidget(self.encounter_json_status)
        self.encounter_json_text = self._build_readonly_text(minimum_height=400)
        self.encounter_json_text.setObjectName("encounterJsonText")
        layout.addWidget(self.encounter_json_text, stretch=1)
        self.encounter_json_export_button = self._sidebar_button(
            "Export JSON",
            self._export_encounter_json,
        )
        layout.addWidget(self.encounter_json_export_button)
        return page

    def _build_group(self, title: str) -> QFrame:
        group = QFrame()
        group.setObjectName("panel")
        group.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        return group

    def _framed_panel(self, title: str) -> QFrame:
        panel = self._build_group(title)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        return panel

    def _build_untitled_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("untitledPanel")
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        return panel

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

    def _sidebar_button(self, label: str, callback) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName("sidebarButton")
        button.clicked.connect(callback)
        return button

    def refresh_view(self) -> None:
        presentation = build_session_presentation(self.session)
        self._presentation = presentation
        if presentation.encounter is None:
            self._pending_target_mode = None
            self._action_menu_scope = None

        self.scene_text.setPlainText(presentation.story_text or "")
        self._sync_rest_buttons(presentation)

        if presentation.encounter is None:
            self.scene_group.show()
            self.story_choices_group.show()
            self.encounter_panel.hide()
            self.victory_overlay.hide()
            self.battlefield_widget.set_area_overlay(None)
            self._render_story_actions(presentation.story_actions)
        else:
            self.scene_group.hide()
            self.story_choices_group.hide()
            self.encounter_panel.show()
            self._sync_combat_log_round(presentation.scene_id)
            self._render_encounter(presentation)
        self._sync_victory_overlay(presentation)
        self._sync_encounter_json_view()
        self._schedule_ai_step_if_needed()

    def _render_story_actions(self, actions: list[ActionView]) -> None:
        clear_layout(self.story_choices_layout)
        for action in actions:
            if action.kind in {"system_short_rest", "system_long_rest"}:
                continue
            button = QPushButton(action.label)
            button.clicked.connect(
                lambda _checked=False, action_index=action.index: self._select_action(action_index)
            )
            self.story_choices_layout.addWidget(button)
        self.story_choices_layout.addStretch(1)

    def _render_encounter(self, presentation: SessionPresentation) -> None:
        encounter = presentation.encounter
        assert encounter is not None
        self.battlefield_widget.set_battlefield(encounter.battlefield)

        target_modes = self._target_selection_modes(encounter.non_movement_actions)
        if not self._target_mode_is_available(encounter.non_movement_actions, target_modes):
            self._pending_target_mode = None
        self.battlefield_widget.set_cell_targeting_enabled(
            self._pending_area_spell_action(encounter.non_movement_actions) is not None
        )
        self.battlefield_widget.set_area_overlay(
            self._pending_spell_overlay(encounter.non_movement_actions)
        )
        selected_targetable_actions = (
            target_modes.get(self._pending_target_mode, {}) if self._pending_target_mode is not None else {}
        )
        targetable_refs = {
            target_ref
            for action in selected_targetable_actions.values()
            if (target_ref := self._target_actor_ref(action)) is not None
        }
        self.battlefield_widget.set_targeting_state(targetable_refs)

        for direction, button in self.movement_buttons.items():
            action = encounter.movement_actions.get(direction)
            button.setEnabled(action is not None)

        self._render_movement_status(encounter.resources)
        self._render_initiative_rail(encounter.resources)

        action_groups = self._action_groups(encounter.non_movement_actions)
        if self._action_menu_scope is not None and encounter.action_pane_title != "Actions":
            self._action_menu_scope = None
        if (
            self._action_menu_scope is not None
            and not action_groups.get(self._action_menu_scope.economy, {}).get(
                self._action_menu_scope.bucket,
            )
        ):
            self._action_menu_scope = None

        self.encounter_actions_layout.removeWidget(self.movement_group)
        self.movement_group.setParent(None)
        clear_layout(self.encounter_actions_layout)
        rendered_target_modes: set[TargetSelectionMode] = set()
        if encounter.action_pane_title != "Actions":
            self.encounter_actions_layout.addWidget(self.movement_group)
            self._render_action_detail_column(
                encounter.action_pane_title,
                encounter.non_movement_actions,
                rendered_target_modes,
                scope=None,
            )
            self.encounter_actions_layout.addStretch(1)
        else:
            self.encounter_actions_layout.addWidget(self.movement_group)
            self._render_action_economy_column(
                title="Actions",
                economy="action",
                bucket_actions=action_groups["action"],
                available=encounter.resources.action_status == "Ready",
                rendered_target_modes=rendered_target_modes,
                indicator_color="#2f6f9d",
            )
            self._render_action_economy_column(
                title="Bonus Actions",
                economy="bonus_action",
                bucket_actions=action_groups["bonus_action"],
                available=encounter.resources.bonus_action_status == "Ready",
                rendered_target_modes=rendered_target_modes,
                indicator_color="#c9a227",
            )
            self._render_feature_column(encounter.feature_actions, rendered_target_modes)
            self._render_status_column(encounter.resources)

        if encounter.end_turn_action is None:
            self.end_turn_button.setEnabled(False)
            self.end_turn_button.setText("End Turn")
        else:
            self.end_turn_button.setEnabled(True)
            self.end_turn_button.setText(
                "Pass Reaction" if encounter.end_turn_action.kind == "pass" else "End Turn"
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
            self._select_action(action.index)

    def _render_action_economy_column(
        self,
        title: str,
        economy: str,
        bucket_actions: dict[str, list[ActionView]],
        available: bool,
        rendered_target_modes: set[TargetSelectionMode],
        indicator_color: str,
    ) -> None:
        if self._action_menu_scope is not None and self._action_menu_scope.economy == economy:
            self._render_action_detail_column(
                self._action_scope_title(self._action_menu_scope),
                bucket_actions[self._action_menu_scope.bucket],
                rendered_target_modes,
                scope=self._action_menu_scope,
            )
            return
        self._render_action_menu_column(title, economy, bucket_actions, available, indicator_color)

    def _render_action_menu_column(
        self,
        title: str,
        economy: str,
        bucket_actions: dict[str, list[ActionView]],
        available: bool,
        indicator_color: str,
    ) -> None:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)
        column_layout.addWidget(self._build_action_header(title, available, indicator_color))

        for bucket_key, bucket_title in self._action_buckets():
            actions = bucket_actions[bucket_key]
            button = QPushButton(bucket_title)
            button.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
            button.setEnabled(bool(actions))
            button.clicked.connect(
                lambda _checked=False, selected_economy=economy, selected_bucket=bucket_key: (
                    self._open_action_menu(selected_economy, selected_bucket)
                )
            )
            column_layout.addWidget(button)

        column_layout.addStretch(1)
        self.encounter_actions_layout.addWidget(column, stretch=1)

    def _render_action_detail_column(
        self,
        title: str,
        actions: list[ActionView],
        rendered_target_modes: set[TargetSelectionMode],
        scope: ActionMenuScope | None,
    ) -> None:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)
        header = QLabel(title)
        header_font = QFont()
        header_font.setBold(True)
        header.setFont(header_font)
        column_layout.addWidget(header)

        if not actions:
            empty = QLabel("None")
            empty.setEnabled(False)
            column_layout.addWidget(empty)
        for action in actions:
            button = self._build_encounter_action_button(action, rendered_target_modes)
            if button is not None:
                column_layout.addWidget(button)
        column_layout.addStretch(1)
        if scope is not None:
            back = QPushButton("Back")
            back.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
            back.clicked.connect(lambda _checked=False, selected_scope=scope: self._close_action_menu(selected_scope))
            column_layout.addWidget(back)
        self.encounter_actions_layout.addWidget(column, stretch=1)

    def _render_feature_column(
        self,
        feature_actions: list[ActionView],
        rendered_target_modes: set[TargetSelectionMode],
    ) -> None:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)

        column_layout.addWidget(
            self._build_action_header(
                "Class Features",
                bool(feature_actions),
                "#9c8b68",
                show_indicator=False,
            )
        )

        if not feature_actions:
            empty = QLabel("None")
            empty.setEnabled(False)
            column_layout.addWidget(empty)
        else:
            for action in feature_actions:
                widget = self._build_feature_action_widget(action, rendered_target_modes)
                if widget is not None:
                    column_layout.addWidget(widget)

        column_layout.addStretch(1)
        self.encounter_actions_layout.addWidget(column, stretch=1)

    def _render_status_column(self, resources) -> None:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)

        header = QLabel("Status")
        header_font = QFont()
        header_font.setBold(True)
        header.setFont(header_font)
        column_layout.addWidget(header)
        column_layout.addWidget(
            self._build_resource_bar(
                resources.current_health,
                resources.max_health,
                "#9d2f2f",
                f"{resources.current_health} / {resources.max_health} HP",
                height=RESOURCE_BAR_HEIGHT,
            )
        )
        if resources.spell_slots:
            column_layout.addWidget(self._build_spell_slot_section(resources))
        conditions = QLabel(f"Conditions: {', '.join(condition.capitalize() for condition in resources.conditions) if resources.conditions else 'None'}")
        conditions.setWordWrap(True)
        column_layout.addWidget(conditions)
        column_layout.addStretch(1)
        self.encounter_actions_layout.addWidget(column, stretch=1)

    def _render_movement_status(self, resources) -> None:
        clear_layout(self.movement_status_layout)
        self.movement_status_layout.addWidget(
            self._build_resource_bar(
                resources.movement_remaining_feet,
                resources.movement_total_feet,
                "#2f6f9d",
                f"{resources.movement_remaining_feet}/{resources.movement_total_feet} ft",
                height=RESOURCE_BAR_HEIGHT,
            )
        )

    def _render_initiative_rail(self, resources) -> None:
        clear_layout(self.initiative_layout)
        if not resources.initiative:
            empty = QLabel("No initiative order.")
            empty.setEnabled(False)
            self.initiative_layout.addWidget(empty)
            self.initiative_layout.addStretch(1)
            return
        for index, entry in enumerate(resources.initiative, start=1):
            self.initiative_layout.addWidget(
                self._build_initiative_entry_widget(index, entry)
            )
        self.initiative_layout.addStretch(1)

    def _build_initiative_entry_widget(self, index: int, entry) -> QWidget:
        card = QFrame()
        card.setObjectName("initiativeCard")
        card.setProperty("active", entry.is_active)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        top_row = QWidget()
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        rank = QLabel(f"#{index}")
        rank.setObjectName("initiativeRank")
        top_layout.addWidget(rank)

        top_layout.addStretch(1)
        if entry.is_active:
            badge = QLabel("ACTING")
            badge.setObjectName("initiativeBadge")
            top_layout.addWidget(badge)

        layout.addWidget(top_row)

        name = QLabel(entry.label)
        name.setObjectName("initiativeName")
        name.setWordWrap(True)
        layout.addWidget(name)

        score = QLabel(f"Initiative {entry.total}")
        score.setObjectName("initiativeScore")
        layout.addWidget(score)
        return card

    def _build_action_header(
        self,
        title: str,
        available: bool,
        indicator_color: str,
        *,
        show_indicator: bool = True,
    ) -> QWidget:
        container = QWidget()
        container.setObjectName("actionHeader")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if show_indicator:
            indicator = QFrame()
            indicator.setFixedSize(10, 10)
            if available:
                indicator.setStyleSheet(
                    f"QFrame {{ background: {indicator_color}; border: 1px solid {indicator_color}; border-radius: 5px; }}"
                )
            else:
                indicator.setStyleSheet(
                    "QFrame { background: #9d2f2f; border: 1px solid #9d2f2f; border-radius: 5px; }"
                )
            layout.addWidget(indicator)

        header = QLabel(title)
        header.setObjectName("sectionTitle")
        header_font = QFont()
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)
        layout.addStretch(1)
        return container

    def _build_resource_bar(
        self,
        current: int,
        maximum: int,
        color: str,
        value_text: str,
        height: int = 24,
    ) -> QWidget:
        container = QWidget()
        container.setFixedHeight(height)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QFrame()
        bar.setMinimumHeight(height)
        bar.setMaximumHeight(height)
        bar.setStyleSheet(
            "QFrame {"
            "border: 1px solid #9c8b68;"
            "background: #efe4c8;"
            "border-radius: 4px;"
            "}"
        )
        bar_layout = QGridLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(0)
        filled = QFrame()
        filled.setStyleSheet(f"QFrame {{ background: {color}; border-radius: 3px; }}")
        empty = QFrame()
        empty.setStyleSheet("QFrame { background: transparent; }")
        filled_units = max(0, min(current, maximum))
        empty_units = max(0, maximum - filled_units)
        bar_layout.addWidget(filled, 0, 0)
        bar_layout.addWidget(empty, 0, 1)
        bar_layout.setColumnStretch(0, max(filled_units, 1 if maximum == 0 else 0))
        bar_layout.setColumnStretch(1, max(empty_units, 1 if maximum == 0 else 0))
        value = QLabel(value_text, bar)
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value.setStyleSheet("QLabel { color: white; font-weight: bold; background: transparent; }")
        bar_layout.addWidget(value, 0, 0, 1, 2)
        layout.addWidget(bar)
        return container

    def _build_spell_slot_section(self, resources) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        title = QLabel("Spell Slots")
        title.setStyleSheet("QLabel { font-weight: 600; }")
        layout.addWidget(title)
        for track in resources.spell_slots:
            row = QLabel(spell_slot_rich_text(track.level, track.remaining, track.maximum))
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setStyleSheet("QLabel { font-family: Menlo, Monaco, monospace; }")
            layout.addWidget(row)
        return container

    def _build_encounter_action_button(
        self,
        action: ActionView,
        rendered_target_modes: set[TargetSelectionMode],
    ) -> QPushButton | None:
        target_mode = self._target_mode_for_action(action)
        if target_mode is not None:
            if target_mode in rendered_target_modes:
                return None
            rendered_target_modes.add(target_mode)
            button = QPushButton(self._target_mode_label(target_mode))
            button.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
            button.setCheckable(True)
            button.setChecked(target_mode == self._pending_target_mode)
            if action.index < 0:
                button.setEnabled(False)
                return button
            button.clicked.connect(
                lambda _checked=False, mode=target_mode: self._toggle_target_action(mode)
            )
            return button

        button = QPushButton(action.label)
        button.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
        if action.index < 0:
            button.setEnabled(False)
            return button
        button.clicked.connect(
            lambda _checked=False, action_index=action.index: self._select_action(action_index)
        )
        return button

    def _build_feature_action_widget(
        self,
        action: ActionView,
        rendered_target_modes: set[TargetSelectionMode],
    ) -> QPushButton | None:
        button = self._build_encounter_action_button(action, rendered_target_modes)
        if button is None:
            return None
        dot = (
            "🟡"
            if action.cost.get("bonus_action", 0) > 0
            else "🔵"
            if action.cost.get("action", 0) > 0
            else "🔴"
            if action.cost.get("reaction", 0) > 0
            else "⚪"
        )
        if action.cost.get("bonus_action", 0) > 0:
            button.setText(f"{button.text()}  {dot}")
        else:
            button.setText(f"{button.text()}  {dot}")
        return button

    def _action_groups(
        self,
        actions: list[ActionView],
    ) -> dict[str, dict[str, list[ActionView]]]:
        groups = {
            economy: {bucket: [] for bucket, _ in self._action_buckets()}
            for economy in ("action", "bonus_action", "reaction")
        }
        for action in actions:
            groups[self._action_economy_key(action)][self._action_bucket_key(action)].append(action)
        return groups

    def _action_buckets(self) -> tuple[tuple[str, str], ...]:
        return (
            ("attack", "Attack"),
            ("magic", "Magic"),
            ("class", "Class"),
            ("utilize", "Utilize"),
            ("other", "Other"),
        )

    def _open_action_menu(self, economy: str, bucket: str) -> None:
        self._pending_target_mode = None
        self._action_menu_scope = ActionMenuScope(economy=economy, bucket=bucket)
        self.refresh_view()

    def _close_action_menu(self, scope: ActionMenuScope | None = None) -> None:
        self._pending_target_mode = None
        if scope is not None and self._action_menu_scope != scope:
            return
        self._action_menu_scope = None
        self.refresh_view()

    def _action_scope_title(self, scope: ActionMenuScope) -> str:
        economy_title = "Bonus Actions" if scope.economy == "bonus_action" else "Actions"
        bucket_title = dict(self._action_buckets())[scope.bucket]
        return f"{economy_title} / {bucket_title}"

    def _action_economy_key(self, action: ActionView) -> str:
        if action.cost.get("bonus_action", 0) > 0:
            return "bonus_action"
        if action.cost.get("reaction", 0) > 0 or action.kind in {"opportunity_attack", "pass"}:
            return "reaction"
        return "action"

    def _action_bucket_key(self, action: ActionView) -> str:
        if action.kind in {"attack", "opportunity_attack", "grapple"}:
            return "attack"
        if action.kind in {"magic", "spell"}:
            return "magic"
        if action.kind == "feature":
            return "class"
        if action.kind == "utilize":
            return "utilize"
        return "other"

    def _trigger_move(self, direction: str) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        self._pending_target_mode = None
        self._action_menu_scope = None
        action = self._presentation.encounter.movement_actions.get(direction)
        if action is not None:
            self._select_action(action.index)

    def _end_turn(self) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        self._pending_target_mode = None
        self._action_menu_scope = None
        action = self._presentation.encounter.end_turn_action
        if action is not None:
            self._select_action(action.index)

    def _system_save(self) -> None:
        if self._presentation is None:
            return
        self._select_action(self._presentation.system_actions[0].index)

    def _system_load(self) -> None:
        if self._presentation is None:
            return
        self._select_action(self._presentation.system_actions[1].index)

    def _trigger_rest(self, kind: str) -> None:
        if self._presentation is None or self._presentation.encounter is not None:
            return
        action = next(
            (action for action in self._presentation.story_actions if action.kind == kind),
            None,
        )
        if action is not None:
            self._select_action(action.index)

    def _sync_rest_buttons(self, presentation: SessionPresentation) -> None:
        if not hasattr(self, "short_rest_button"):
            return
        if presentation.encounter is not None:
            self.short_rest_button.hide()
            self.long_rest_button.hide()
            return
        rest_actions = {action.kind: action for action in presentation.story_actions}
        short_rest_action = rest_actions.get("system_short_rest")
        long_rest_action = rest_actions.get("system_long_rest")
        self.short_rest_button.setVisible(short_rest_action is not None)
        self.long_rest_button.setVisible(long_rest_action is not None)
        self.short_rest_button.setEnabled(short_rest_action is not None)
        self.long_rest_button.setEnabled(long_rest_action is not None)

    def _select_action(self, index: int) -> None:
        self._pending_target_mode = None
        self._action_menu_scope = None
        result = self.session.choose(index)
        self._apply_turn_result(result)

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
            self._select_action(action.index)

    def _toggle_target_action(self, mode: TargetSelectionMode) -> None:
        self._pending_target_mode = None if self._pending_target_mode == mode else mode
        self.refresh_view()

    def _handle_battlefield_actor_clicked(self, actor_ref: str) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        if self._pending_target_mode is None:
            return
        action = self._target_selection_modes(self._presentation.encounter.non_movement_actions).get(
            self._pending_target_mode,
            {},
        ).get(
            actor_ref
        )
        if action is None:
            return
        self._select_action(action.index)

    def _handle_battlefield_cell_clicked(self, x: int, y: int) -> None:
        self._handle_battlefield_point_clicked(x + 0.5, y + 0.5)

    def _handle_battlefield_point_clicked(self, x: float, y: float) -> None:
        if self._presentation is None or self._presentation.encounter is None:
            return
        action = self._pending_area_spell_action(self._presentation.encounter.non_movement_actions)
        if action is None:
            return
        if self.session.encounter_state is None:
            return
        payload = spell_action_value(
            parse_spell_action_value(str(action.value))[0],
            aim_point=(x, y),
        )
        encounter_action = EncounterAction(
            label=action.label,
            kind=action.kind,
            value=payload,
            id=action.id,
            actor_ref=action.actor_ref,
            cost=ActionCost(
                movement=action.cost.get("movement", 0),
                action=action.cost.get("action", 0),
                bonus_action=action.cost.get("bonus_action", 0),
                reaction=action.cost.get("reaction", 0),
            ),
            source_trigger_id=action.source_trigger_id,
        )
        self._pending_target_mode = None
        self._action_menu_scope = None
        result = self.session.choose_encounter_action(encounter_action)
        self._apply_turn_result(result)

    def _target_selection_modes(
        self,
        actions: list[ActionView],
    ) -> dict[TargetSelectionMode, dict[str, ActionView]]:
        modes: dict[TargetSelectionMode, dict[str, ActionView]] = {}
        for action in actions:
            target_mode = self._target_mode_for_action(action)
            target_actor_ref = self._target_actor_ref(action)
            if target_mode is None or target_actor_ref is None:
                continue
            modes.setdefault(target_mode, {})[target_actor_ref] = action
        return modes

    def _target_mode_for_action(self, action: ActionView) -> TargetSelectionMode | None:
        if action.kind == "spell" and self._is_area_spell_action(action):
            return TargetSelectionMode(
                kind=action.kind,
                source_trigger_id=action.id,
            )
        if self._target_actor_ref(action) is None:
            return None
        return TargetSelectionMode(
            kind=action.kind,
            source_trigger_id=action.source_trigger_id,
        )

    def _target_mode_label(self, mode: TargetSelectionMode) -> str:
        if mode.kind == "spell" and self._presentation is not None and self._presentation.encounter is not None:
            action = self._pending_area_spell_action(
                self._presentation.encounter.non_movement_actions,
                mode=mode,
            )
            if action is not None:
                return action.label
        return "Opportunity attack" if mode.kind == "opportunity_attack" else "Attack"

    def _target_actor_ref(self, action: ActionView | None) -> str | None:
        if action is None or action.kind not in {"attack", "opportunity_attack"}:
            return None
        if isinstance(action.value, str):
            return action.value
        if not isinstance(action.value, int):
            return None
        return f"enemy:{action.value}"

    def _is_area_spell_action(self, action: ActionView) -> bool:
        if action.kind != "spell" or not isinstance(action.value, str):
            return False
        spell_id, target_ref, aim_cell = parse_spell_action_value(action.value)
        if not spell_id or target_ref is not None or aim_cell is not None:
            return False
        spell = self._spell_by_id(spell_id)
        if spell is None:
            return True
        return spell is not None and spell.geometry_mode in {"directional_area", "point_area"}

    def _pending_area_spell_action(
        self,
        actions: list[ActionView],
        *,
        mode: TargetSelectionMode | None = None,
    ) -> ActionView | None:
        pending_mode = mode or self._pending_target_mode
        if pending_mode is None or pending_mode.kind != "spell":
            return None
        return next(
            (
                action
                for action in actions
                if action.kind == "spell"
                and action.id == pending_mode.source_trigger_id
                and self._is_area_spell_action(action)
            ),
            None,
        )

    def _target_mode_is_available(
        self,
        actions: list[ActionView],
        target_modes: dict[TargetSelectionMode, dict[str, ActionView]],
    ) -> bool:
        if self._pending_target_mode is None:
            return False
        if self._pending_target_mode in target_modes:
            return True
        return self._pending_area_spell_action(actions) is not None

    def _apply_turn_result(self, result) -> None:
        encounter_state = self.session.encounter_state
        was_in_encounter = (
            self._presentation is not None and self._presentation.encounter is not None
        )
        is_combat_result = was_in_encounter or encounter_state is not None
        if (
            encounter_state is not None
            and self._combat_log_scene_id != encounter_state.scene_id
        ):
            self._sync_combat_log_round(encounter_state.scene_id)
        if is_combat_result:
            roll_views = build_roll_views(result.events)
            messages = without_roll_details(result.messages)
            self.dice_roll_panel.append_entry(messages, roll_views)
            if messages or roll_views:
                QTimer.singleShot(20, self._scroll_roll_log_to_bottom)

        if result.should_exit:
            self.close()
            return
        self.refresh_view()

    def _sync_combat_log_round(self, scene_id: str) -> None:
        encounter_state = self.session.encounter_state
        if encounter_state is None:
            return
        if self._combat_log_scene_id != scene_id:
            self.dice_roll_panel.clear_log()
            self._combat_log_scene_id = scene_id
            self._logged_round_number = None
        if self._logged_round_number == encounter_state.round_number:
            return
        self.dice_roll_panel.start_round(encounter_state.round_number)
        self._logged_round_number = encounter_state.round_number
        QTimer.singleShot(20, self._scroll_roll_log_to_bottom)

    def _pending_spell_overlay(self, actions: list[ActionView]) -> dict[str, object] | None:
        action = self._pending_area_spell_action(actions)
        if action is None or self.session.encounter_state is None or self.session.player.spellcasting is None:
            return None
        spell_id, _, _ = parse_spell_action_value(str(action.value))
        spell = self._spell_by_id(spell_id)
        if spell is None:
            return None
        grid = Grid(
            width=self.session.encounter_state.definition.grid.width,
            height=self.session.encounter_state.definition.grid.height,
        )
        if spell.geometry_mode == "point_area":
            radius_feet = spell.area_size_feet
            if radius_feet is None:
                return None
            radius_squares = max(
                1,
                radius_feet // self.session.player.attributes.movement.feet_per_square,
            )
            return serialize_area(build_radius_area(Position(0, 0), radius_squares, grid))
        length = spell_range_squares(spell, self.session.player)
        if length is None:
            return None
        origin = Position(
            self.session.encounter_state.player_position.x,
            self.session.encounter_state.player_position.y,
        )
        default_direction = Vector2D(1.0, 0.0)
        coverage_threshold = (
            self.session.encounter_state.rules_config.directional_aoe_cell_coverage_threshold
        )
        return serialize_area(
            build_directional_area(
                spell.range_data.get("type"),
                origin,
                default_direction,
                length,
                grid,
                coverage_threshold=coverage_threshold,
            )
        )

    def _spell_by_id(self, spell_id: str):
        session = getattr(self, "session", None)
        if session is None or session.player.spellcasting is None:
            return None
        return next(
            (spell for spell in session.player.spellcasting.learned_spells if spell.id == spell_id),
            None,
        )

    def _scroll_roll_log_to_bottom(self) -> None:
        scrollbar = self.roll_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _schedule_ai_step_if_needed(self) -> None:
        state = self.session.encounter_state
        if (
            self._ai_step_scheduled
            or state is None
            or self.session.pending_scene_transition is not None
            or not state.needs_ai_advance()
        ):
            return
        self._ai_step_scheduled = True
        QTimer.singleShot(500, self._advance_ai_step)

    def _advance_ai_step(self) -> None:
        self._ai_step_scheduled = False
        state = self.session.encounter_state
        if state is None or not state.needs_ai_advance():
            return
        self._apply_turn_result(self.session.advance_ai())

    def show_menu_root(self) -> None:
        self.sidebar_stack.setCurrentIndex(0)

    def show_inventory(self) -> None:
        items = self.session.player.inventory.items
        inventory_text = (
            "Inventory is empty."
            if not items
            else "\n".join(self.display_item_name(item_id) for item_id in items)
        )
        self.inventory_text.setPlainText(inventory_text)
        self.sidebar_stack.setCurrentIndex(1)

    def show_attributes(self) -> None:
        player = self.session.player
        attributes = player.attributes
        attributes_text = "\n".join(
            [
                f"Name: {player.name}",
                f"HP: {player.get_health()}/{player.get_max_health()}",
                f"AC: {player.get_armor_class()}",
                f"Level: {attributes.level}",
                f"STR: {attributes.strength}",
                f"DEX: {attributes.dexterity}",
                f"CON: {attributes.constitution}",
                f"WIS: {attributes.wisdom}",
                f"INT: {attributes.intelligence}",
                f"CHA: {attributes.charisma}",
                f"PB: +{attributes.proficiency_bonus}",
            ]
        )
        self.attributes_text.setPlainText(attributes_text)
        self.sidebar_stack.setCurrentIndex(2)

    def show_system_menu(self) -> None:
        self.sidebar_stack.setCurrentIndex(3)

    def show_encounter_json(self) -> None:
        if not self._show_encounter_json:
            return
        self.sidebar_stack.setCurrentIndex(4)

    def display_item_name(self, item_id: str) -> str:
        item = self._items_by_id.get(item_id)
        return item.name if item else item_id

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_victory_overlay_geometry()

    def _sync_encounter_json_view(self) -> None:
        if not self._show_encounter_json or not hasattr(self, "encounter_json_text"):
            return
        payload = self._encounter_json_payload()
        encounter_active = bool(payload.get("encounter_active"))
        self.encounter_json_status.setText(
            "Live encounter state." if encounter_active else "No active encounter."
        )
        self.encounter_json_text.setPlainText(
            json.dumps(payload, indent=2, sort_keys=True)
        )
        self.encounter_json_export_button.setEnabled(bool(payload))

    def _encounter_json_payload(self) -> dict[str, object]:
        encounter_state = self.session.encounter_state
        if encounter_state is None:
            return {
                "encounter_active": False,
                "scene_id": self.session.current_scene_id,
                "scene_text": self.session.current_scene.text,
            }
        return {
            "encounter_active": True,
            "encounter": encounter_state.export_state(self.session.player),
        }

    def _export_encounter_json(self) -> None:
        payload = self._encounter_json_payload()
        default_name = self._default_encounter_json_export_name(payload)
        target_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Encounter JSON",
            default_name,
            "JSON Files (*.json);;All Files (*)",
        )
        if not target_path:
            return
        with open(target_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        QMessageBox.information(self, "Export Complete", f"Saved JSON to:\n{target_path}")

    def _default_encounter_json_export_name(self, payload: dict[str, object]) -> str:
        scene_id = payload.get("encounter", {}).get("scene_id") if isinstance(
            payload.get("encounter"),
            dict,
        ) else None
        suffix = scene_id if isinstance(scene_id, str) and scene_id else "no-encounter"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"encounter-{suffix}-{timestamp}.json"


class ScenarioPickerWindow(QMainWindow):
    def __init__(
        self,
        start_scene_override: str | None = None,
        *,
        show_encounter_json: bool = False,
    ):
        _require_pyside6()
        super().__init__()
        self._start_scene_override = start_scene_override
        self._show_encounter_json = show_encounter_json
        self._game_window: CyoaPySide6Window | None = None
        self.setWindowTitle("Choose Scenario")
        self.resize(520, 420)

        central = QWidget()
        central.setObjectName("rootCentral")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Choose a scenario")
        title.setObjectName("windowTitle")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel("Start a new session from any available scenario.")
        subtitle.setObjectName("sectionSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        scenarios = list_scenarios()
        if not scenarios:
            empty = QLabel("No valid scenarios were found in app/content/scenarios/.")
            empty.setWordWrap(True)
            layout.addWidget(empty)
            return

        for scenario in scenarios:
            button = QPushButton(f"{scenario.label} ({scenario.id})")
            button.setObjectName("sidebarButton")
            button.setMinimumHeight(44)
            button.clicked.connect(
                lambda _checked=False, selected=scenario: self._open_scenario(selected)
            )
            layout.addWidget(button)
        layout.addStretch(1)

    def _open_scenario(self, scenario: ScenarioInfo) -> None:
        self._game_window = CyoaPySide6Window(
            Game(
                str(scenario.directory),
                start_scene=self._start_scene_override,
            ),
            show_encounter_json=self._show_encounter_json,
        )
        self._game_window.show()
        self.close()


def run_pyside6_app(
    game: Game | None = None,
    start_scene_override: str | None = None,
    show_encounter_json: bool = False,
) -> None:
    _require_pyside6()
    app = QApplication.instance() or QApplication(sys.argv)
    apply_fantasy_theme(app)
    window = (
        CyoaPySide6Window(game=game, show_encounter_json=show_encounter_json)
        if game is not None
        else ScenarioPickerWindow(
            start_scene_override=start_scene_override,
            show_encounter_json=show_encounter_json,
        )
    )
    window.show()
    app.exec()
