"""Primary story and battlefield surface for the Qt frontend."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from srd_arena.application.observations import ActionObservation
from ...shared.models import InitiativeTrackEntryView
from .encounter import BattlefieldWidget, clear_layout
from .encounter.initiative import InitiativeRail

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class GameSurfaceCallbacks:
    """Window-owned interactions emitted by the main game surface."""

    select_story_action: Callable[[str], None]
    creature_clicked: Callable[[str, bool], None]
    cell_clicked: Callable[[int, int], None]
    point_clicked: Callable[[float, float], None]
    interaction_cancelled: Callable[[], None]
    continue_transition: Callable[[], None]


class GameSurface(QWidget):
    """Own story panels, battlefield widgets, and the victory overlay."""

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

        self._scene_group, scene_layout = _build_group()
        self._scene_group.setObjectName("scenePanel")
        self._scene_text = _readonly_text(minimum_height=180)
        self._scene_text.setObjectName("sceneText")
        scene_layout.addWidget(self._scene_text)

        self._story_choices_group, story_group_layout = _build_group()
        self._story_choices_group.setObjectName("choicesPanel")
        self._story_choices_layout = QVBoxLayout()
        self._story_choices_layout.setSpacing(8)
        story_group_layout.addWidget(
            _wrap_in_scroll(self._story_choices_layout)
        )

        self._encounter_panel = QWidget()
        self._encounter_panel.setObjectName("encounterPanel")
        encounter_layout = QVBoxLayout(self._encounter_panel)
        encounter_layout.setContentsMargins(0, 0, 0, 0)
        encounter_layout.setSpacing(10)
        encounter_layout.addWidget(
            self._build_battlefield_area(image_root),
            stretch=1,
        )
        self._build_victory_overlay()

        layout.addWidget(self._scene_group, stretch=1)
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
        story_text: str | None,
        actions: Sequence[ActionObservation],
    ) -> None:
        """Present a non-encounter scene and its choices."""

        self._scene_text.setPlainText(story_text or "")
        self._scene_group.show()
        self._story_choices_group.show()
        self._encounter_panel.hide()
        self._victory_overlay.hide()
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

        self._scene_group.hide()
        self._story_choices_group.hide()
        self._encounter_panel.show()

    def sync_victory_overlay(
        self,
        message: str | None,
        *,
        can_continue: bool,
    ) -> None:
        """Show or hide the encounter transition overlay."""

        if message is None:
            self._victory_overlay.hide()
            return
        self._victory_overlay_message.setText(message)
        self._victory_overlay_button.setEnabled(can_continue)
        self._update_victory_overlay_geometry()
        self._victory_overlay.show()
        self._victory_overlay.raise_()

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

    def _build_victory_overlay(self) -> None:
        self._victory_overlay = QFrame(self._encounter_panel)
        self._victory_overlay.setObjectName("victoryOverlay")
        self._victory_overlay.setStyleSheet(
            "QFrame { background: rgba(12, 10, 6, 190); }"
            "QLabel { color: #f6edd9; }"
            "QPushButton { min-width: 140px; min-height: 40px; }"
        )
        self._victory_overlay.hide()
        overlay_layout = QVBoxLayout(self._victory_overlay)
        overlay_layout.setContentsMargins(40, 40, 40, 40)
        overlay_layout.setSpacing(12)
        overlay_layout.addStretch(1)
        overlay_card = QFrame()
        overlay_card.setObjectName("overlayCard")
        overlay_card.setStyleSheet(
            "QFrame { background: #1d1710; border: 2px solid #c9a227; "
            "border-radius: 10px; }"
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
        self._victory_overlay_message = QLabel("")
        self._victory_overlay_message.setObjectName("transitionMessage")
        self._victory_overlay_message.setWordWrap(True)
        self._victory_overlay_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_card_layout.addWidget(self._victory_overlay_message)
        self._victory_overlay_button = QPushButton("Continue")
        self._victory_overlay_button.setObjectName("transitionButton")
        self._victory_overlay_button.clicked.connect(
            self._callbacks.continue_transition
        )
        overlay_card_layout.addWidget(
            self._victory_overlay_button,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        overlay_layout.addWidget(overlay_card, alignment=Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addStretch(1)

    def _update_victory_overlay_geometry(self) -> None:
        self._victory_overlay.setGeometry(self._encounter_panel.rect())

    def resizeEvent(self, event) -> None:  # pragma: no cover - Qt geometry event
        super().resizeEvent(event)
        self._update_victory_overlay_geometry()


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


def _readonly_text(*, minimum_height: int) -> QTextEdit:
    text = QTextEdit()
    text.setReadOnly(True)
    text.setMinimumHeight(minimum_height)
    return text
