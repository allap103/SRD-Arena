"""Primary story and battlefield surface for the Qt frontend."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from srd_arena.engine.api import ActionObservation

from ..presentation.models import InitiativeTrackEntryView
from .encounter import BattlefieldWidget, clear_layout
from .encounter.initiative import InitiativeRail


@dataclass(frozen=True)
class GameSurfaceCallbacks:
    """Window-owned interactions emitted by the main game surface."""

    select_story_action: Callable[[str], None]
    creature_clicked: Callable[[str, bool], None]
    cell_clicked: Callable[[int, int], None]
    point_clicked: Callable[[float, float], None]
    interaction_cancelled: Callable[[], None]
    restart_encounter: Callable[[], None]


class GameSurface(QWidget):
    """Own story panels, battlefield widgets, and the completion overlay."""

    def __init__(
        self,
        callbacks: GameSurfaceCallbacks,
        *,
        image_root: Path | None = None,
    ) -> None:
        super().__init__()
        self._callbacks = callbacks
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._story_choices_group, story_group_layout = _build_group()
        self._story_choices_group.setObjectName("choicesPanel")
        self._story_choices_layout = QVBoxLayout()
        self._story_choices_layout.setSpacing(8)
        story_group_layout.addWidget(_wrap_in_scroll(self._story_choices_layout))

        self._encounter_panel = QWidget()
        self._encounter_panel.setObjectName("encounterPanel")
        encounter_layout = QVBoxLayout(self._encounter_panel)
        encounter_layout.setContentsMargins(0, 0, 0, 0)
        encounter_layout.setSpacing(10)
        encounter_layout.addWidget(
            self._build_battlefield_area(image_root),
            stretch=1,
        )
        self._build_completion_overlay()

        layout.addWidget(self._story_choices_group, stretch=1)
        layout.addWidget(self._encounter_panel, stretch=2)

    @property
    def battlefield(self) -> BattlefieldWidget:
        """Return the battlefield widget used by encounter interaction."""

        return self._battlefield

    def render_initiative(
        self,
        entries: Sequence[InitiativeTrackEntryView],
    ) -> None:
        """Render initiative through the rail owned by this surface."""

        self._initiative_rail.set_entries(entries)

    def show_story(
        self,
        actions: Sequence[ActionObservation],
    ) -> None:
        """Present choices outside an active encounter."""

        self._story_choices_group.show()
        self._encounter_panel.hide()
        self._completion_overlay.hide()
        self._battlefield.set_area_overlay(None)
        clear_layout(self._story_choices_layout)
        for action in actions:
            button = QPushButton(action.label)
            button.clicked.connect(
                lambda _checked=False, action_id=action.id: (
                    self._callbacks.select_story_action(action_id)
                )
            )
            self._story_choices_layout.addWidget(button)
        self._story_choices_layout.addStretch(1)

    def show_encounter(self) -> None:
        """Switch the primary surface from story panels to the battlefield."""

        self._story_choices_group.hide()
        self._encounter_panel.show()

    def sync_completion_overlay(
        self,
        visible: bool,
        *,
        can_restart: bool,
    ) -> None:
        """Show or hide the encounter-completion overlay."""

        if not visible:
            self._completion_overlay.hide()
            return
        self._completion_overlay_button.setEnabled(can_restart)
        self._update_completion_overlay_geometry()
        self._completion_overlay.show()
        self._completion_overlay.raise_()

    def _build_battlefield_area(self, image_root: Path | None) -> QWidget:
        battlefield_area = QWidget()
        battlefield_layout = QHBoxLayout(battlefield_area)
        battlefield_layout.setContentsMargins(0, 0, 0, 0)
        battlefield_layout.setSpacing(10)

        self._battlefield = BattlefieldWidget(image_root=image_root)
        self._battlefield.setObjectName("combatBoard")
        self._battlefield.creature_clicked.connect(self._callbacks.creature_clicked)
        self._battlefield.cell_clicked.connect(self._callbacks.cell_clicked)
        self._battlefield.point_clicked.connect(self._callbacks.point_clicked)
        self._battlefield.interaction_cancelled.connect(
            self._callbacks.interaction_cancelled
        )

        self._initiative_rail = InitiativeRail()
        battlefield_layout.addWidget(self._initiative_rail)
        battlefield_layout.addWidget(self._battlefield, stretch=1)
        return battlefield_area

    def _build_completion_overlay(self) -> None:
        self._completion_overlay = QFrame(self._encounter_panel)
        self._completion_overlay.setObjectName("completionOverlay")
        self._completion_overlay.setStyleSheet(
            "QFrame {"
            " background: rgba(12, 10, 6, 230);"
            " border: 1px solid #756344;"
            " border-radius: 6px;"
            "}"
            "QPushButton { min-width: 140px; min-height: 40px; }"
        )
        self._completion_overlay.hide()
        overlay_layout = QVBoxLayout(self._completion_overlay)
        overlay_layout.setContentsMargins(16, 16, 16, 16)
        self._completion_overlay_button = QPushButton("Restart encounter")
        self._completion_overlay_button.setObjectName("restartButton")
        self._completion_overlay_button.clicked.connect(
            self._callbacks.restart_encounter
        )
        overlay_layout.addWidget(
            self._completion_overlay_button,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

    def _update_completion_overlay_geometry(self) -> None:
        self._completion_overlay.resize(self._completion_overlay.sizeHint())
        popup_geometry = self._completion_overlay.rect()
        popup_geometry.moveCenter(self._encounter_panel.rect().center())
        self._completion_overlay.setGeometry(popup_geometry)

    def resizeEvent(self, event: QResizeEvent) -> None:  # pragma: no cover
        super().resizeEvent(event)
        self._update_completion_overlay_geometry()


def _build_group() -> tuple[QFrame, QVBoxLayout]:
    group = QFrame()
    group.setObjectName("panel")
    group.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QVBoxLayout(group)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(8)
    return group, layout


def _wrap_in_scroll(content_layout: QVBoxLayout) -> QScrollArea:
    container = QWidget()
    container.setLayout(content_layout)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(container)
    return scroll
