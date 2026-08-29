"""Render encounter controls without owning game orchestration."""

from __future__ import annotations

import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from srd_arena.application.api import ActionObservation, GameObservation

from ...presentation.models import EncounterView, ResourceSummaryView
from .action_menus import group_actions
from .config import (
    ENCOUNTER_BUTTON_HEIGHT,
    RESOURCE_BAR_HEIGHT,
    ActionMenuScope,
    TargetSelectionMode,
)
from .layout import clear_layout
from .resource_formatting import spell_slot_rich_text
from .targeting import (
    actions_for_mode,
    allocation_status,
    mode_for_action,
    mode_label,
)


@dataclass(frozen=True)
class EncounterPanelBindings:
    """Widgets populated by :class:`EncounterPanelRenderer`."""

    health_layout: QVBoxLayout
    movement_layout: QVBoxLayout
    actions_layout: QVBoxLayout
    bonus_actions_layout: QVBoxLayout
    features_layout: QVBoxLayout
    status_layout: QVBoxLayout
    end_turn_button: QPushButton
    accordion_toggles: Mapping[str, QToolButton]


@dataclass(frozen=True)
class EncounterPanelCallbacks:
    """Window-owned interactions emitted by encounter controls."""

    select_action: Callable[[str], None]
    toggle_target: Callable[[TargetSelectionMode], None]
    open_action_menu: Callable[[str, str], None]
    close_action_menu: Callable[[ActionMenuScope | None], None]
    set_resource_allocation: Callable[[str, int], None]


class EncounterPanelRenderer:
    """Populate encounter controls from GUI presentation models."""

    def __init__(
        self,
        bindings: EncounterPanelBindings,
        callbacks: EncounterPanelCallbacks,
    ) -> None:
        self._bindings = bindings
        self._callbacks = callbacks
        self._actions: tuple[ActionObservation, ...] = ()
        self._pending_target_mode: TargetSelectionMode | None = None
        self._action_menu_scope: ActionMenuScope | None = None

    def render(
        self,
        encounter: EncounterView,
        observation: GameObservation,
        *,
        pending_target_mode: TargetSelectionMode | None,
        action_menu_scope: ActionMenuScope | None,
    ) -> ActionMenuScope | None:
        """Render one encounter snapshot and return its still-valid menu scope."""

        self._actions = tuple(encounter.non_movement_actions)
        self._pending_target_mode = pending_target_mode
        action_groups = group_actions(encounter.non_movement_actions)
        self._action_menu_scope = _valid_action_menu_scope(
            action_menu_scope,
            encounter,
            action_groups,
        )

        self._render_resource_summary(encounter.resources)
        self._set_accordion_status("Actions", encounter.resources.action_status)
        self._set_accordion_status(
            "Bonus Actions",
            encounter.resources.bonus_action_status,
        )
        for layout in (
            self._bindings.actions_layout,
            self._bindings.bonus_actions_layout,
            self._bindings.features_layout,
            self._bindings.status_layout,
        ):
            clear_layout(layout)

        targeting_status = allocation_status(observation)
        if targeting_status is not None:
            self._render_allocation_status(targeting_status)
            self._render_resource_allocation_controls(observation, encounter)

        rendered_target_modes: set[TargetSelectionMode] = set()
        if encounter.action_pane_title != "Actions":
            self._render_action_detail_column(
                encounter.action_pane_title,
                encounter.non_movement_actions,
                rendered_target_modes,
                scope=None,
                target_layout=self._bindings.actions_layout,
            )
        else:
            self._render_action_economy_column(
                economy="action",
                bucket_actions=action_groups["action"],
                rendered_target_modes=rendered_target_modes,
                target_layout=self._bindings.actions_layout,
            )
            self._render_action_economy_column(
                economy="bonus_action",
                bucket_actions=action_groups["bonus_action"],
                rendered_target_modes=rendered_target_modes,
                target_layout=self._bindings.bonus_actions_layout,
            )
            self._render_feature_column(
                encounter.feature_actions,
                rendered_target_modes,
                self._bindings.features_layout,
            )
        self._render_status_column(
            encounter.resources,
            self._bindings.status_layout,
        )
        self._render_end_turn(encounter)
        return self._action_menu_scope

    def _render_action_economy_column(
        self,
        economy: str,
        bucket_actions: dict[str, list[ActionObservation]],
        rendered_target_modes: set[TargetSelectionMode],
        target_layout: QVBoxLayout,
    ) -> None:
        if (
            self._action_menu_scope is not None
            and self._action_menu_scope.economy == economy
            and self._action_menu_scope.bucket == "magic"
        ):
            self._render_spell_browser(
                bucket_actions["magic"],
                rendered_target_modes,
                target_layout,
            )
            return
        actions = [
            action
            for bucket in bucket_actions.values()
            for action in bucket
            if action.kind not in {"spell", "feature"}
        ]
        spells = [
            action for action in bucket_actions["magic"] if action.kind == "spell"
        ]
        self._render_direct_actions(
            actions,
            spells,
            economy,
            rendered_target_modes,
            target_layout,
        )

    def _render_direct_actions(
        self,
        actions: Sequence[ActionObservation],
        spells: list[ActionObservation],
        economy: str,
        rendered_target_modes: set[TargetSelectionMode],
        target_layout: QVBoxLayout,
    ) -> None:
        for action in actions:
            button = self._build_action_button(action, rendered_target_modes)
            if button is not None:
                target_layout.addWidget(button)

        spell_ids = {action.source_id for action in spells if action.source_id}
        if spell_ids:
            spells_button = QPushButton(f"Spells ({len(spell_ids)})")
            spells_button.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
            spells_button.clicked.connect(
                lambda _checked=False, selected_economy=economy: (
                    self._callbacks.open_action_menu(selected_economy, "magic")
                )
            )
            target_layout.addWidget(spells_button)

        if not actions and not spell_ids:
            empty = QLabel("None")
            empty.setEnabled(False)
            target_layout.addWidget(empty)

    def _render_spell_browser(
        self,
        actions: list[ActionObservation],
        rendered_target_modes: set[TargetSelectionMode],
        target_layout: QVBoxLayout,
    ) -> None:
        header = QLabel("Spells")
        header.setObjectName("sectionSubtitle")
        target_layout.addWidget(header)

        search = QLineEdit()
        search.setPlaceholderText("Search spells...")
        target_layout.addWidget(search)

        spell_actions: dict[tuple[str, int | None], ActionObservation] = {}
        spell_details: dict[str, tuple[str, int | None]] = {}
        for action in actions:
            spell_id = action.source_id
            if spell_id is None:
                continue
            slot_level = action.resource_level
            spell_actions.setdefault((spell_id, slot_level), action)
            spell_details[spell_id] = (
                action.source_label or action.label,
                action.source_level,
            )

        level_filter = QComboBox()
        level_filter.addItem("All levels", None)
        for spell_level in sorted(
            level for _name, level in spell_details.values() if level is not None
        ):
            level_filter.addItem(
                "Cantrips" if spell_level == 0 else f"Level {spell_level}",
                spell_level,
            )
        target_layout.addWidget(level_filter)

        rows: list[tuple[QPushButton, str, int | None]] = []
        for (spell_id, slot_level), action in sorted(
            spell_actions.items(),
            key=lambda item: (
                spell_details[item[0][0]][1]
                if item[0][0] in spell_details
                and spell_details[item[0][0]][1] is not None
                else 99,
                spell_details[item[0][0]][0].casefold()
                if item[0][0] in spell_details
                else item[1].label.casefold(),
                item[0][1] or 0,
            ),
        ):
            spell = spell_details.get(spell_id)
            button = self._build_action_button(action, rendered_target_modes)
            if button is None:
                continue
            name = spell[0] if spell is not None else action.label
            if slot_level is not None:
                name = f"{name} (Level {slot_level})"
            row_level = spell[1] if spell is not None else None
            set_compact_button_text(button, name)
            target_layout.addWidget(button)
            rows.append((button, name.casefold(), row_level))

        def apply_filters() -> None:
            query = search.text().strip().casefold()
            selected_level = level_filter.currentData()
            for button, name, level in rows:
                button.setVisible(
                    (not query or query in name)
                    and (selected_level is None or level == selected_level)
                )

        search.textChanged.connect(lambda _text: apply_filters())
        level_filter.currentIndexChanged.connect(lambda _index: apply_filters())

        back = QPushButton("Back")
        back.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
        back.clicked.connect(
            lambda _checked=False: self._callbacks.close_action_menu(
                self._action_menu_scope
            )
        )
        target_layout.addWidget(back)

    def _render_action_detail_column(
        self,
        title: str,
        actions: Sequence[ActionObservation],
        rendered_target_modes: set[TargetSelectionMode],
        scope: ActionMenuScope | None,
        target_layout: QVBoxLayout,
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
            button = self._build_action_button(action, rendered_target_modes)
            if button is not None:
                column_layout.addWidget(button)
        column_layout.addStretch(1)
        if scope is not None:
            back = QPushButton("Back")
            back.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
            back.clicked.connect(
                lambda _checked=False, selected_scope=scope: (
                    self._callbacks.close_action_menu(selected_scope)
                )
            )
            column_layout.addWidget(back)
        target_layout.addWidget(column)

    def _render_feature_column(
        self,
        feature_actions: Sequence[ActionObservation],
        rendered_target_modes: set[TargetSelectionMode],
        target_layout: QVBoxLayout,
    ) -> None:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)

        if not feature_actions:
            empty = QLabel("None")
            empty.setEnabled(False)
            column_layout.addWidget(empty)
        else:
            for action in feature_actions:
                widget = self._build_feature_action_widget(
                    action,
                    rendered_target_modes,
                )
                if widget is not None:
                    column_layout.addWidget(widget)

        column_layout.addStretch(1)
        target_layout.addWidget(column)

    def _render_status_column(
        self,
        resources: ResourceSummaryView,
        target_layout: QVBoxLayout,
    ) -> None:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)

        if resources.spell_slots:
            column_layout.addWidget(_build_spell_slot_section(resources))
        conditions_text = (
            ", ".join(condition.capitalize() for condition in resources.conditions)
            if resources.conditions
            else "None"
        )
        conditions = QLabel(f"Conditions: {conditions_text}")
        conditions.setWordWrap(True)
        column_layout.addWidget(conditions)
        column_layout.addStretch(1)
        target_layout.addWidget(column)

    def _render_resource_summary(self, resources: ResourceSummaryView) -> None:
        clear_layout(self._bindings.movement_layout)
        self._bindings.movement_layout.addWidget(
            _build_resource_bar(
                resources.movement_remaining_feet,
                resources.movement_total_feet,
                "#2f6f9d",
                f"{resources.movement_remaining_feet}/{resources.movement_total_feet} ft",
                height=RESOURCE_BAR_HEIGHT,
            )
        )
        clear_layout(self._bindings.health_layout)
        self._bindings.health_layout.addWidget(
            _build_resource_bar(
                resources.current_health,
                resources.max_health,
                "#9d2f2f",
                f"{resources.current_health} / {resources.max_health} HP",
                height=RESOURCE_BAR_HEIGHT,
            )
        )

    def _build_action_button(
        self,
        action: ActionObservation,
        rendered_target_modes: set[TargetSelectionMode],
    ) -> QPushButton | None:
        target_mode = mode_for_action(action)
        if target_mode is not None:
            if target_mode in rendered_target_modes:
                return None
            rendered_target_modes.add(target_mode)
            mode_actions = actions_for_mode(self._actions, target_mode)
            button = QPushButton(mode_label(target_mode, mode_actions))
            button.setFixedHeight(ENCOUNTER_BUTTON_HEIGHT)
            button.setCheckable(True)
            button.setChecked(target_mode == self._pending_target_mode)
            configure_action_button(button, mode_actions)
            if button.isEnabled():
                button.clicked.connect(
                    lambda _checked=False, mode=target_mode: (
                        self._callbacks.toggle_target(mode)
                    )
                )
            return button

        button = QPushButton(action.label)
        set_compact_button_text(button, action.label)
        configure_action_button(button, [action])
        if button.isEnabled():
            button.clicked.connect(
                lambda _checked=False, action_id=action.id: (
                    self._callbacks.select_action(action_id)
                )
            )
        return button

    def _build_feature_action_widget(
        self,
        action: ActionObservation,
        rendered_target_modes: set[TargetSelectionMode],
    ) -> QPushButton | None:
        button = self._build_action_button(action, rendered_target_modes)
        if button is None:
            return None
        dot = (
            "\U0001f7e1"
            if action.cost.get("bonus_action", 0) > 0
            else "\U0001f535"
            if action.cost.get("action", 0) > 0
            else "\U0001f534"
            if action.cost.get("reaction", 0) > 0
            else "\u26aa"
        )
        button.setText(f"{button.text()}  {dot}")
        return button

    def _set_accordion_status(self, title: str, text: str) -> None:
        toggle = self._bindings.accordion_toggles.get(title)
        if toggle is None:
            return
        availability_dot = "\u26aa" if text in {"Spent", "Waiting"} else "\U0001f7e2"
        toggle.setText(f"{title} {availability_dot}")

    def _render_allocation_status(self, status: str) -> None:
        label = QLabel(status)
        label.setObjectName("targetAllocationStatus")
        label.setWordWrap(True)
        label.setToolTip(
            "Click a highlighted target to allocate. "
            "Shift-click removes one allocation; right-click cancels."
        )
        self._bindings.actions_layout.addWidget(label)

    def _render_resource_allocation_controls(
        self,
        observation: GameObservation,
        encounter: EncounterView,
    ) -> None:
        pending = (
            observation.encounter.targeting
            if observation.encounter is not None
            else None
        )
        if pending is None or pending.resource_pool_total is None:
            return
        allocations = {
            item.target_ref: item.amount for item in pending.resource_allocations
        }
        allocated_total = sum(allocations.values())
        for limit in pending.resource_limits:
            target_ref = limit.target_ref
            missing_hit_points = limit.maximum
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            target = encounter.battlefield.creatures
            target_name = next(
                creature.name
                for creature in target
                if creature.creature_ref == target_ref
            )
            label = QLabel(f"{target_name} ({missing_hit_points} missing)")
            spin = QSpinBox()
            current = allocations.get(target_ref, 0)
            remaining_with_current = (
                pending.resource_pool_total - allocated_total + current
            )
            maximum = min(missing_hit_points, remaining_with_current)
            spin.setRange(0, maximum)
            spin.setValue(current)
            spin.setSuffix(" HP")
            spin.setToolTip(f"Allocate 0\u2013{maximum} Hit Points to this creature.")
            spin.editingFinished.connect(
                lambda ref=target_ref, control=spin: (
                    self._callbacks.set_resource_allocation(ref, control.value())
                )
            )
            layout.addWidget(label, 1)
            layout.addWidget(spin)
            self._bindings.actions_layout.addWidget(row)

    def _render_end_turn(self, encounter: EncounterView) -> None:
        action = encounter.end_turn_action
        self._bindings.end_turn_button.setEnabled(action is not None)
        self._bindings.end_turn_button.setText(
            "Pass Reaction"
            if action is not None and action.kind == "pass"
            else "End Turn"
        )


def configure_action_button(
    button: QPushButton,
    actions: list[ActionObservation],
) -> None:
    """Apply availability and explanatory tooltip state to an action button."""

    availability = (
        "available"
        if any(action.enabled for action in actions)
        else "unimplemented"
        if any(action.availability == "unimplemented" for action in actions)
        else "unavailable"
    )
    reasons = tuple(
        dict.fromkeys(
            reason for action in actions for reason in action.unavailable_reasons
        )
    )
    button.setProperty("availability", availability)
    button.setEnabled(availability == "available")
    if reasons and availability != "available":
        heading = (
            "Not implemented:" if availability == "unimplemented" else "Unavailable:"
        )
        button.setToolTip(
            "\n".join((heading, *(f"\u2022 {reason}" for reason in reasons)))
        )


def set_compact_button_text(button: QPushButton, label: str) -> None:
    """Wrap a long action label to at most two compact button lines."""

    lines = textwrap.wrap(
        label,
        width=28,
        max_lines=2,
        placeholder="...",
    ) or [label]
    button.setText("\n".join(lines))
    button.setFixedHeight(
        ENCOUNTER_BUTTON_HEIGHT if len(lines) == 1 else ENCOUNTER_BUTTON_HEIGHT * 2 - 6
    )


def _build_resource_bar(
    current: int,
    maximum: int,
    color: str,
    value_text: str,
    *,
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
        "QFrame {border: 1px solid #9c8b68;background: #efe4c8;border-radius: 4px;}"
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
    value.setStyleSheet(
        "QLabel { color: white; font-weight: bold; background: transparent; }"
    )
    bar_layout.addWidget(value, 0, 0, 1, 2)
    layout.addWidget(bar)
    return container


def _build_spell_slot_section(resources: ResourceSummaryView) -> QWidget:
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


def _valid_action_menu_scope(
    scope: ActionMenuScope | None,
    encounter: EncounterView,
    action_groups: Mapping[str, Mapping[str, list[ActionObservation]]],
) -> ActionMenuScope | None:
    if scope is None or encounter.action_pane_title != "Actions":
        return None
    return scope if action_groups.get(scope.economy, {}).get(scope.bucket) else None
