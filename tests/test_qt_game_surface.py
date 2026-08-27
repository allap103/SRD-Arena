from __future__ import annotations

import os
from collections.abc import Callable

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QPushButton,
    QTextEdit,
    QWidget,
)

from srd_arena.application.observations import ActionObservation
from srd_arena.frontends.gui.ui.game_surface import (
    GameSurface,
    GameSurfaceCallbacks,
)
from srd_arena.frontends.shared.models import InitiativeTrackEntryView


def test_game_surface_switches_between_story_and_encounter() -> None:
    app = _application()
    selected_actions: list[str] = []
    surface = GameSurface(_callbacks(select_story_action=selected_actions.append))
    surface.show()
    story_action = ActionObservation(
        id="enter-encounter",
        label="Enter encounter",
        kind="story",
        creature_ref="",
    )

    surface.show_story("An encounter awaits.", [story_action])
    app.processEvents()

    scene_text = surface.findChild(QTextEdit, "sceneText")
    choice = next(
        button
        for button in surface.findChildren(QPushButton)
        if button.text() == "Enter encounter"
    )
    encounter_panel = surface.findChild(QWidget, "encounterPanel")
    assert scene_text.toPlainText() == "An encounter awaits."
    assert encounter_panel.isHidden()

    choice.click()
    assert selected_actions == ["enter-encounter"]

    surface.show_encounter()
    app.processEvents()
    assert not encounter_panel.isHidden()
    assert surface.findChild(QFrame, "scenePanel").isHidden()
    assert surface.findChild(QFrame, "choicesPanel").isHidden()

    _dispose(surface, app)


def test_game_surface_owns_transition_overlay_behavior() -> None:
    app = _application()
    continued: list[bool] = []
    surface = GameSurface(
        _callbacks(continue_transition=lambda: continued.append(True))
    )
    surface.resize(900, 600)
    surface.show()
    surface.show_encounter()

    surface.sync_victory_overlay("The encounter is over.", can_continue=True)
    app.processEvents()

    overlay = surface.findChild(QFrame, "victoryOverlay")
    message = surface.findChild(QLabel, "transitionMessage")
    button = surface.findChild(QPushButton, "transitionButton")
    encounter_panel = surface.findChild(QWidget, "encounterPanel")
    assert not overlay.isHidden()
    assert message.text() == "The encounter is over."
    assert button.isEnabled()
    assert overlay.geometry() == encounter_panel.rect()

    button.click()
    assert continued == [True]

    surface.sync_victory_overlay(None, can_continue=False)
    assert overlay.isHidden()

    _dispose(surface, app)


def test_game_surface_renders_initiative_through_its_rail() -> None:
    app = _application()
    surface = GameSurface(_callbacks())
    surface.render_initiative(
        (
            InitiativeTrackEntryView("wizard", "Wizard", 18, is_active=True),
            InitiativeTrackEntryView("goblin", "Goblin", 12),
        )
    )

    cards = surface.findChildren(QFrame, "initiativeCard")
    names = surface.findChildren(QLabel, "initiativeName")
    assert len(cards) == 2
    assert [name.text() for name in names] == ["Wizard", "Goblin"]
    assert cards[0].property("active") is True
    assert cards[1].property("active") is False

    _dispose(surface, app)


def _callbacks(
    *,
    select_story_action: Callable[[str], None] | None = None,
    continue_transition: Callable[[], None] | None = None,
) -> GameSurfaceCallbacks:
    return GameSurfaceCallbacks(
        select_story_action=select_story_action or (lambda _action_id: None),
        creature_clicked=lambda _creature_ref, _remove: None,
        cell_clicked=lambda _x, _y: None,
        point_clicked=lambda _x, _y: None,
        interaction_cancelled=lambda: None,
        continue_transition=continue_transition or (lambda: None),
    )


def _application() -> QApplication:
    instance = QApplication.instance()
    return instance if isinstance(instance, QApplication) else QApplication([])


def _dispose(surface: GameSurface, app: QApplication) -> None:
    surface.close()
    surface.deleteLater()
    app.processEvents()
