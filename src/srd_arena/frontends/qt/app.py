from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
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
    CreatureObservation,
    EncounterObservation,
    GameObservation,
)
from ...application.scenarios import ScenarioPresentation
from ..shared.dice import build_roll_views, without_roll_details
from ..shared.models import SessionPresentation
from ..shared.session import build_session_presentation
from .ui.encounter import (
    ENCOUNTER_BUTTON_HEIGHT,
    ActionMenuScope,
    BattlefieldWidget,
    DiceRollPanel,
    TargetSelectionMode,
    clear_layout,
)
from .ui.encounter.movement import (
    MovementPlan,
    build_movement_plan,
    movement_plan_is_current,
)
from .ui.encounter.panel_renderer import (
    EncounterPanelBindings,
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


EXIT_CHOICE_TEXT = "Exit game"


try:
    from PySide6.QtCore import QSize, Qt, QTimer, Signal
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QFrame,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QStackedWidget,
        QTextEdit,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency at runtime

    def Signal(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    QApplication = None  # type: ignore[assignment]
    QCheckBox = object  # type: ignore[assignment]
    QSize = object  # type: ignore[assignment]
    Qt = object  # type: ignore[assignment]
    QTimer = object  # type: ignore[assignment]
    QFont = object  # type: ignore[assignment]
    QFrame = object  # type: ignore[assignment]
    QFileDialog = object  # type: ignore[assignment]
    QHBoxLayout = object  # type: ignore[assignment]
    QLabel = object  # type: ignore[assignment]
    QMainWindow = object  # type: ignore[assignment]
    QMessageBox = object  # type: ignore[assignment]
    QPushButton = object  # type: ignore[assignment]
    QScrollArea = object  # type: ignore[assignment]
    QSizePolicy = object  # type: ignore[assignment]
    QStackedWidget = object  # type: ignore[assignment]
    QTextEdit = object  # type: ignore[assignment]
    QToolButton = object  # type: ignore[assignment]
    QVBoxLayout = object  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]
SIDEBAR_WIDTH = 320


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
        self._show_encounter_json = show_encounter_json
        self._show_team_outlines = True
        self._always_show_creature_names = False
        self._team_outline_toggles: list[QCheckBox] = []
        self._creature_name_toggles: list[QCheckBox] = []
        self._movement_plan: MovementPlan | None = None
        self._accordion_toggles: dict[str, QToolButton] = {}

        self.setWindowTitle("SRD Arena")
        self.resize(1400, 900)

        central = QWidget()
        central.setObjectName("rootCentral")
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._build_main_content(), stretch=1)
        root_layout.addWidget(self._build_sidebar())
        self._encounter_panel_renderer = EncounterPanelRenderer(
            EncounterPanelBindings(
                health_layout=self.health_status_layout,
                movement_layout=self.movement_status_layout,
                initiative_layout=self.initiative_layout,
                actions_layout=self.actions_section_layout,
                bonus_actions_layout=self.bonus_actions_section_layout,
                features_layout=self.features_section_layout,
                status_layout=self.status_section_layout,
                end_turn_button=self.end_turn_button,
                accordion_toggles=self._accordion_toggles,
            ),
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
        self.combat_sidebar_index = self.sidebar_stack.addWidget(
            self._build_combat_sidebar_page()
        )
        if self._show_encounter_json:
            self.encounter_json_sidebar_index = self.sidebar_stack.addWidget(
                self._build_encounter_json_page()
            )
        layout.addWidget(self.sidebar_stack)
        return sidebar

    def _build_sidebar_root(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._sidebar_button("Attributes", self.show_attributes))
        layout.addWidget(self._sidebar_button("Inventory", self.show_inventory))
        layout.addWidget(self._sidebar_button("System", self.show_system_menu))
        layout.addStretch(1)
        return page

    def _build_combat_sidebar_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)

        resource_summary = QFrame()
        resource_summary.setObjectName("accordionSection")
        resource_layout = QVBoxLayout(resource_summary)
        resource_layout.setContentsMargins(8, 8, 8, 8)
        resource_layout.setSpacing(6)
        self.health_status = QWidget()
        self.health_status_layout = QVBoxLayout(self.health_status)
        self.health_status_layout.setContentsMargins(0, 0, 0, 0)
        resource_layout.addWidget(self.health_status)
        self.movement_status = QWidget()
        self.movement_status_layout = QVBoxLayout(self.movement_status)
        self.movement_status_layout.setContentsMargins(0, 0, 0, 0)
        resource_layout.addWidget(self.movement_status)
        page_layout.addWidget(resource_summary)

        scroll = QScrollArea()
        scroll.setObjectName("combatSidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        actions_section, self.actions_section_layout = self._build_collapsible_section(
            "Actions",
            expanded=False,
        )
        content_layout.addWidget(actions_section)
        bonus_section, self.bonus_actions_section_layout = (
            self._build_collapsible_section("Bonus Actions", expanded=False)
        )
        content_layout.addWidget(bonus_section)
        features_section, self.features_section_layout = (
            self._build_collapsible_section("Features", expanded=False)
        )
        content_layout.addWidget(features_section)
        status_section, self.status_section_layout = self._build_collapsible_section(
            "Status",
            expanded=False,
        )
        content_layout.addWidget(status_section)

        attributes_section, attributes_layout = self._build_collapsible_section(
            "Attributes",
            expanded=False,
        )
        self.combat_attributes_text = self._build_readonly_text(
            minimum_height=180,
            maximum_height=260,
        )
        attributes_layout.addWidget(self.combat_attributes_text)
        content_layout.addWidget(attributes_section)

        inventory_section, inventory_layout = self._build_collapsible_section(
            "Inventory",
            expanded=False,
        )
        self.combat_inventory_text = self._build_readonly_text(
            minimum_height=140,
            maximum_height=240,
        )
        inventory_layout.addWidget(self.combat_inventory_text)
        content_layout.addWidget(inventory_section)

        system_section, system_layout = self._build_collapsible_section(
            "System",
            expanded=False,
        )
        if self._show_encounter_json:
            system_layout.addWidget(
                self._sidebar_button("Encounter JSON", self.show_encounter_json)
            )
        system_layout.addWidget(self._build_team_outline_toggle())
        system_layout.addWidget(self._build_creature_name_toggle())
        system_layout.addWidget(self._sidebar_button(EXIT_CHOICE_TEXT, self.close))
        content_layout.addWidget(system_section)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        page_layout.addWidget(scroll, stretch=1)

        log_section = QFrame()
        log_section.setObjectName("accordionSection")
        log_layout = QVBoxLayout(log_section)
        log_layout.setContentsMargins(8, 8, 8, 8)
        log_layout.setSpacing(6)
        log_title = QLabel("Combat Log")
        log_title.setObjectName("sectionSubtitle")
        log_layout.addWidget(log_title)
        self.dice_roll_panel = DiceRollPanel(self._select_action_by_id)
        self.roll_scroll = QScrollArea()
        self.roll_scroll.setWidgetResizable(True)
        self.roll_scroll.setMinimumHeight(180)
        self.roll_scroll.setWidget(self.dice_roll_panel)
        log_layout.addWidget(self.roll_scroll)
        page_layout.addWidget(log_section)

        self.end_turn_button = QPushButton("End Turn")
        self.end_turn_button.setObjectName("endTurnButton")
        self.end_turn_button.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
        self.end_turn_button.clicked.connect(self._end_turn)
        page_layout.addWidget(self.end_turn_button)
        return page

    def _build_collapsible_section(
        self,
        title: str,
        *,
        expanded: bool,
    ) -> tuple[QWidget, QVBoxLayout]:
        section = QFrame()
        section.setObjectName("accordionSection")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("accordionHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        toggle = QToolButton()
        toggle.setObjectName("accordionToggle")
        toggle.setProperty(
            "centered",
            title in {"Actions", "Bonus Actions"},
        )
        toggle.setText(title)
        toggle.setCheckable(True)
        toggle.setChecked(expanded)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        header_layout.addWidget(toggle, stretch=1)
        self._accordion_toggles[title] = toggle
        section_layout.addWidget(header)

        body = QWidget()
        body.setObjectName("accordionBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(8)
        body.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        body.setVisible(expanded)
        section_layout.addWidget(body)

        def set_expanded(checked: bool) -> None:
            body.setVisible(checked)
            toggle.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )
            section.updateGeometry()

        toggle.toggled.connect(set_expanded)
        return section, body_layout

    def _build_team_outline_toggle(self) -> QCheckBox:
        toggle = QCheckBox("Show team outlines")
        toggle.setChecked(self._show_team_outlines)
        toggle.toggled.connect(self._set_team_outlines_visible)
        self._team_outline_toggles.append(toggle)
        return toggle

    def _build_creature_name_toggle(self) -> QCheckBox:
        toggle = QCheckBox("Always show creature names")
        toggle.setChecked(self._always_show_creature_names)
        toggle.toggled.connect(self._set_always_show_creature_names)
        self._creature_name_toggles.append(toggle)
        return toggle

    def _set_team_outlines_visible(self, visible: bool) -> None:
        self._show_team_outlines = visible
        self.battlefield_widget.set_team_outlines_visible(visible)
        self._sync_board_setting_toggles(self._team_outline_toggles, visible)

    def _set_always_show_creature_names(self, visible: bool) -> None:
        self._always_show_creature_names = visible
        self.battlefield_widget.set_always_show_creature_names(visible)
        self._sync_board_setting_toggles(self._creature_name_toggles, visible)

    @staticmethod
    def _sync_board_setting_toggles(
        toggles: list[QCheckBox],
        checked: bool,
    ) -> None:
        for toggle in toggles:
            toggle.blockSignals(True)
            toggle.setChecked(checked)
            toggle.blockSignals(False)

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
        if self._show_encounter_json:
            layout.addWidget(
                self._sidebar_button("Encounter JSON", self.show_encounter_json)
            )
        layout.addWidget(self._build_team_outline_toggle())
        layout.addWidget(self._build_creature_name_toggle())
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
        presentation = self._build_session_presentation()
        self._presentation = presentation
        if presentation.encounter is None:
            self._pending_target_mode = None
            self._action_menu_scope = None

        self.scene_text.setPlainText(presentation.story_text or "")

        if presentation.encounter is None:
            if self.sidebar_stack.currentIndex() == self.combat_sidebar_index:
                self.sidebar_stack.setCurrentIndex(0)
            self.scene_group.show()
            self.story_choices_group.show()
            self.encounter_panel.hide()
            self.victory_overlay.hide()
            self.battlefield_widget.set_area_overlay(None)
            self._render_story_actions(presentation.story_actions)
        else:
            if self.sidebar_stack.currentIndex() == 0:
                self.sidebar_stack.setCurrentIndex(self.combat_sidebar_index)
            self.scene_group.hide()
            self.story_choices_group.hide()
            self.encounter_panel.show()
            assert self._observation is not None
            assert self._observation.encounter is not None
            self._sync_combat_log_round(self._observation.encounter)
            self._render_encounter(presentation)
        self._sync_victory_overlay(presentation)
        self._sync_encounter_json_view()
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
        self._sync_combat_sidebar_details()

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
            self.dice_roll_panel.append_entry(messages, roll_views)
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
            self.dice_roll_panel.clear_log()
            self._combat_log_scene_id = encounter.encounter_id
            self._logged_round_number = None
        if self._logged_round_number == encounter.round_number:
            return
        self.dice_roll_panel.start_round(encounter.round_number)
        self._logged_round_number = encounter.round_number
        if entering_encounter:
            creature_ref = encounter.decision.creature_ref
            self.dice_roll_panel.start_turn(
                f"{encounter.creature(creature_ref).name}'s turn"
            )
        QTimer.singleShot(20, self._scroll_roll_log_to_bottom)

    def _scroll_roll_log_to_bottom(self) -> None:
        scrollbar = self.roll_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

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

    def show_menu_root(self) -> None:
        if self._presentation is not None and self._presentation.encounter is not None:
            self.sidebar_stack.setCurrentIndex(self.combat_sidebar_index)
        else:
            self.sidebar_stack.setCurrentIndex(0)

    def show_inventory(self) -> None:
        self.inventory_text.setPlainText(self._inventory_text())
        self.sidebar_stack.setCurrentIndex(1)

    def show_attributes(self) -> None:
        self.attributes_text.setPlainText(self._attributes_text())
        self.sidebar_stack.setCurrentIndex(2)

    def _sync_combat_sidebar_details(self) -> None:
        self.combat_attributes_text.setPlainText(self._attributes_text())
        self.combat_inventory_text.setPlainText(self._inventory_text())

    def _inventory_text(self) -> str:
        actor = self._decision_creature()
        if actor is None or not actor.inventory:
            return "Inventory is empty."
        return "\n".join(item.name for item in actor.inventory)

    def _attributes_text(self) -> str:
        actor = self._decision_creature()
        if actor is None:
            return "No active creature."
        attributes = actor.attributes
        return "\n".join(
            [
                f"Name: {actor.name}",
                f"HP: {actor.health}/{actor.max_health}",
                f"AC: {actor.armor_class}",
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

    def _decision_creature(self) -> CreatureObservation | None:
        observation = self._observation or self.game.observe()
        encounter = observation.encounter
        if encounter is None:
            return None
        return encounter.creature(encounter.decision.creature_ref)

    def show_system_menu(self) -> None:
        self.sidebar_stack.setCurrentIndex(3)

    def show_encounter_json(self) -> None:
        if not self._show_encounter_json:
            return
        self.sidebar_stack.setCurrentIndex(self.encounter_json_sidebar_index)

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
        observation = self._observation or self.game.observe()
        if observation.encounter is None:
            return {
                "encounter_active": False,
                "scene_id": observation.scene.scene_id,
            }
        return {
            "encounter_active": True,
            "encounter": asdict(observation.encounter),
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
        QMessageBox.information(
            self, "Export Complete", f"Saved JSON to:\n{target_path}"
        )

    def _default_encounter_json_export_name(self, payload: dict[str, object]) -> str:
        encounter = payload.get("encounter")
        scene_id = (
            encounter.get("encounter_id") if isinstance(encounter, dict) else None
        )
        suffix = scene_id if isinstance(scene_id, str) and scene_id else "no-encounter"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"encounter-{suffix}-{timestamp}.json"
