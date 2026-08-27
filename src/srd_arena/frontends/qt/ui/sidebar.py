"""Sidebar navigation and auxiliary Qt views."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from srd_arena.application.observations import CreatureObservation, GameObservation
from ...shared.dice import RollView
from .encounter import DiceRollPanel
from .encounter.config import ENCOUNTER_BUTTON_HEIGHT
from .encounter.panel_renderer import EncounterPanelBindings

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
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


SIDEBAR_WIDTH = 320
EXIT_CHOICE_TEXT = "Exit game"


@dataclass(frozen=True)
class SidebarCallbacks:
    """Window-owned operations invoked by sidebar controls."""

    select_log_action: Callable[[str], None]
    end_turn: Callable[[], None]
    close_window: Callable[[], None]
    set_team_outlines_visible: Callable[[bool], None]
    set_creature_names_visible: Callable[[bool], None]


class GameSidebar(QFrame):
    """Own sidebar pages, navigation, settings, and combat-log widgets."""

    def __init__(
        self,
        callbacks: SidebarCallbacks,
        *,
        show_encounter_json: bool = False,
        show_team_outlines: bool = True,
        show_creature_names: bool = False,
    ) -> None:
        super().__init__()
        self._callbacks = callbacks
        self._show_encounter_json = show_encounter_json
        self._encounter_active = False
        self._team_outline_toggles: list[QCheckBox] = []
        self._creature_name_toggles: list[QCheckBox] = []
        self._accordion_toggles: dict[str, QToolButton] = {}
        self._show_team_outlines = show_team_outlines
        self._show_creature_names = show_creature_names
        self._json_payload: dict[str, object] = {}

        self.setObjectName("sidebarPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._stack = QStackedWidget()
        self._root_index = self._stack.addWidget(self._build_root_page())
        self._inventory_index = self._stack.addWidget(self._build_inventory_page())
        self._attributes_index = self._stack.addWidget(self._build_attributes_page())
        self._system_index = self._stack.addWidget(self._build_system_page())
        self._combat_index = self._stack.addWidget(self._build_combat_page())
        self._json_index: int | None = None
        if show_encounter_json:
            self._json_index = self._stack.addWidget(self._build_json_page())
        layout.addWidget(self._stack)

    @property
    def encounter_bindings(self) -> EncounterPanelBindings:
        """Return the widgets populated by the encounter panel renderer."""

        return EncounterPanelBindings(
            health_layout=self._health_layout,
            movement_layout=self._movement_layout,
            actions_layout=self._actions_layout,
            bonus_actions_layout=self._bonus_actions_layout,
            features_layout=self._features_layout,
            status_layout=self._status_layout,
            end_turn_button=self._end_turn_button,
            accordion_toggles=self._accordion_toggles,
        )

    def sync(self, observation: GameObservation) -> None:
        """Refresh auxiliary text and optional JSON from one observation."""

        actor = _decision_creature(observation)
        inventory = inventory_text(actor)
        attributes = attributes_text(actor)
        self._inventory_text.setPlainText(inventory)
        self._attributes_text.setPlainText(attributes)
        self._combat_inventory_text.setPlainText(inventory)
        self._combat_attributes_text.setPlainText(attributes)
        if self._show_encounter_json:
            self._sync_json(observation)

    def enter_encounter(self) -> None:
        """Route the root page to combat when an encounter becomes active."""

        self._encounter_active = True
        if self._stack.currentIndex() == self._root_index:
            self._stack.setCurrentIndex(self._combat_index)

    def leave_encounter(self) -> None:
        """Return from combat controls when no encounter remains active."""

        self._encounter_active = False
        if self._stack.currentIndex() == self._combat_index:
            self._stack.setCurrentIndex(self._root_index)

    def show_root(self) -> None:
        """Show combat controls during encounters and the menu otherwise."""

        self._stack.setCurrentIndex(
            self._combat_index if self._encounter_active else self._root_index
        )

    def show_inventory(self) -> None:
        self._stack.setCurrentIndex(self._inventory_index)

    def show_attributes(self) -> None:
        self._stack.setCurrentIndex(self._attributes_index)

    def show_system(self) -> None:
        self._stack.setCurrentIndex(self._system_index)

    def show_json(self) -> None:
        if self._json_index is not None:
            self._stack.setCurrentIndex(self._json_index)

    def set_team_outlines_checked(self, visible: bool) -> None:
        """Synchronize every duplicate team-outline control."""

        self._show_team_outlines = visible
        _sync_toggles(self._team_outline_toggles, visible)

    def set_creature_names_checked(self, visible: bool) -> None:
        """Synchronize every duplicate creature-name control."""

        self._show_creature_names = visible
        _sync_toggles(self._creature_name_toggles, visible)

    def append_combat_log(
        self,
        messages: Sequence[tuple[str, str]],
        rolls: Sequence[RollView],
    ) -> None:
        self._dice_roll_panel.append_entry(list(messages), list(rolls))

    def clear_combat_log(self) -> None:
        self._dice_roll_panel.clear_log()

    def start_round(self, round_number: int) -> None:
        self._dice_roll_panel.start_round(round_number)

    def start_turn(self, label: str) -> None:
        self._dice_roll_panel.start_turn(label)

    def scroll_combat_log_to_bottom(self) -> None:
        scrollbar = self._roll_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _build_root_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_sidebar_button("Attributes", self.show_attributes))
        layout.addWidget(_sidebar_button("Inventory", self.show_inventory))
        layout.addWidget(_sidebar_button("System", self.show_system))
        layout.addStretch(1)
        return page

    def _build_inventory_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_sidebar_button("Back", self.show_root))
        self._inventory_text = _readonly_text(minimum_height=400)
        layout.addWidget(self._inventory_text, stretch=1)
        return page

    def _build_attributes_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_sidebar_button("Back", self.show_root))
        self._attributes_text = _readonly_text(minimum_height=400)
        layout.addWidget(self._attributes_text, stretch=1)
        return page

    def _build_system_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_sidebar_button("Back", self.show_root))
        if self._show_encounter_json:
            layout.addWidget(_sidebar_button("Encounter JSON", self.show_json))
        layout.addWidget(self._build_team_outline_toggle())
        layout.addWidget(self._build_creature_name_toggle())
        layout.addWidget(_sidebar_button(EXIT_CHOICE_TEXT, self._callbacks.close_window))
        layout.addStretch(1)
        return page

    def _build_json_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_sidebar_button("Back", self.show_system))
        self._json_status = QLabel("Waiting for encounter data.")
        self._json_status.setWordWrap(True)
        layout.addWidget(self._json_status)
        self._json_text = _readonly_text(minimum_height=400)
        self._json_text.setObjectName("encounterJsonText")
        layout.addWidget(self._json_text, stretch=1)
        self._json_export_button = _sidebar_button(
            "Export JSON",
            self._export_json,
        )
        layout.addWidget(self._json_export_button)
        return page

    def _build_combat_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)

        resource_summary = QFrame()
        resource_summary.setObjectName("accordionSection")
        resource_layout = QVBoxLayout(resource_summary)
        resource_layout.setContentsMargins(8, 8, 8, 8)
        resource_layout.setSpacing(6)
        health_status = QWidget()
        self._health_layout = QVBoxLayout(health_status)
        self._health_layout.setContentsMargins(0, 0, 0, 0)
        resource_layout.addWidget(health_status)
        movement_status = QWidget()
        self._movement_layout = QVBoxLayout(movement_status)
        self._movement_layout.setContentsMargins(0, 0, 0, 0)
        resource_layout.addWidget(movement_status)
        page_layout.addWidget(resource_summary)

        scroll = QScrollArea()
        scroll.setObjectName("combatSidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        actions, self._actions_layout = self._build_collapsible_section("Actions")
        content_layout.addWidget(actions)
        bonus_actions, self._bonus_actions_layout = self._build_collapsible_section(
            "Bonus Actions"
        )
        content_layout.addWidget(bonus_actions)
        features, self._features_layout = self._build_collapsible_section("Features")
        content_layout.addWidget(features)
        status, self._status_layout = self._build_collapsible_section("Status")
        content_layout.addWidget(status)

        attributes, attributes_layout = self._build_collapsible_section("Attributes")
        self._combat_attributes_text = _readonly_text(
            minimum_height=180,
            maximum_height=260,
        )
        attributes_layout.addWidget(self._combat_attributes_text)
        content_layout.addWidget(attributes)

        inventory, inventory_layout = self._build_collapsible_section("Inventory")
        self._combat_inventory_text = _readonly_text(
            minimum_height=140,
            maximum_height=240,
        )
        inventory_layout.addWidget(self._combat_inventory_text)
        content_layout.addWidget(inventory)

        system, system_layout = self._build_collapsible_section("System")
        if self._show_encounter_json:
            system_layout.addWidget(_sidebar_button("Encounter JSON", self.show_json))
        system_layout.addWidget(self._build_team_outline_toggle())
        system_layout.addWidget(self._build_creature_name_toggle())
        system_layout.addWidget(
            _sidebar_button(EXIT_CHOICE_TEXT, self._callbacks.close_window)
        )
        content_layout.addWidget(system)
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
        self._dice_roll_panel = DiceRollPanel(self._callbacks.select_log_action)
        self._roll_scroll = QScrollArea()
        self._roll_scroll.setWidgetResizable(True)
        self._roll_scroll.setMinimumHeight(180)
        self._roll_scroll.setWidget(self._dice_roll_panel)
        log_layout.addWidget(self._roll_scroll)
        page_layout.addWidget(log_section)

        self._end_turn_button = QPushButton("End Turn")
        self._end_turn_button.setObjectName("endTurnButton")
        self._end_turn_button.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
        self._end_turn_button.clicked.connect(self._callbacks.end_turn)
        page_layout.addWidget(self._end_turn_button)

        return page

    def _build_collapsible_section(
        self,
        title: str,
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
        toggle.setProperty("centered", title in {"Actions", "Bonus Actions"})
        toggle.setText(title)
        toggle.setCheckable(True)
        toggle.setChecked(False)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.ArrowType.RightArrow)
        header_layout.addWidget(toggle, stretch=1)
        self._accordion_toggles[title] = toggle
        section_layout.addWidget(header)

        body = QWidget()
        body.setObjectName("accordionBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(8)
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        body.hide()
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
        toggle.toggled.connect(self._callbacks.set_team_outlines_visible)
        self._team_outline_toggles.append(toggle)
        return toggle

    def _build_creature_name_toggle(self) -> QCheckBox:
        toggle = QCheckBox("Always show creature names")
        toggle.setChecked(self._show_creature_names)
        toggle.toggled.connect(self._callbacks.set_creature_names_visible)
        self._creature_name_toggles.append(toggle)
        return toggle

    def _sync_json(self, observation: GameObservation) -> None:
        self._json_payload = encounter_json_payload(observation)
        encounter_active = bool(self._json_payload.get("encounter_active"))
        self._json_status.setText(
            "Live encounter state." if encounter_active else "No active encounter."
        )
        self._json_text.setPlainText(
            json.dumps(self._json_payload, indent=2, sort_keys=True)
        )
        self._json_export_button.setEnabled(bool(self._json_payload))

    def _export_json(self) -> None:
        default_name = default_encounter_json_export_name(self._json_payload)
        target_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Encounter JSON",
            default_name,
            "JSON Files (*.json);;All Files (*)",
        )
        if not target_path:
            return
        with open(target_path, "w", encoding="utf-8") as handle:
            json.dump(self._json_payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        QMessageBox.information(
            self,
            "Export Complete",
            f"Saved JSON to:\n{target_path}",
        )


def inventory_text(actor: CreatureObservation | None) -> str:
    """Format the inventory page for the current decision creature."""

    if actor is None or not actor.inventory:
        return "Inventory is empty."
    return "\n".join(item.name for item in actor.inventory)


def attributes_text(actor: CreatureObservation | None) -> str:
    """Format the attributes page for the current decision creature."""

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


def encounter_json_payload(observation: GameObservation) -> dict[str, object]:
    """Build the optional debug representation for one game observation."""

    if observation.encounter is None:
        return {
            "encounter_active": False,
            "scene_id": observation.scene.scene_id,
        }
    return {
        "encounter_active": True,
        "encounter": asdict(observation.encounter),
    }


def default_encounter_json_export_name(payload: dict[str, object]) -> str:
    """Return a timestamped export filename for an encounter payload."""

    encounter = payload.get("encounter")
    scene_id = encounter.get("encounter_id") if isinstance(encounter, dict) else None
    suffix = scene_id if isinstance(scene_id, str) and scene_id else "no-encounter"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"encounter-{suffix}-{timestamp}.json"


def _decision_creature(observation: GameObservation) -> CreatureObservation | None:
    encounter = observation.encounter
    if encounter is None:
        return None
    return encounter.creature(encounter.decision.creature_ref)


def _sidebar_button(label: str, callback: Callable[[], None]) -> QPushButton:
    button = QPushButton(label)
    button.setObjectName("sidebarButton")
    button.clicked.connect(callback)
    return button


def _readonly_text(
    *,
    minimum_height: int,
    maximum_height: int | None = None,
) -> QTextEdit:
    text = QTextEdit()
    text.setReadOnly(True)
    text.setMinimumHeight(minimum_height)
    if maximum_height is not None:
        text.setMaximumHeight(maximum_height)
    return text


def _sync_toggles(toggles: Sequence[QCheckBox], checked: bool) -> None:
    for toggle in toggles:
        toggle.blockSignals(True)
        toggle.setChecked(checked)
        toggle.blockSignals(False)
