from typing import TYPE_CHECKING

from .frontends.shared.models import SceneView, TurnResult
from .runtime.scenario import Scenario
from .runtime.save import (
    SaveGame,
    create_save,
    load_from_file,
    load_from_slot,
    restore_save,
    save_to_file,
    save_to_slot,
)
from .runtime.session import Session
from .frontends.cli.runner import CliRunner

Game = Scenario
GameSession = Session
SceneRunner = CliRunner

if TYPE_CHECKING:
    from .frontends.qt.app import GameWindow
    from .frontends.qt.app import CyoaPySide6Window

try:
    from .frontends.qt.app import GameWindow
    from .frontends.qt.app import CyoaPySide6Window
except ModuleNotFoundError:
    pass

__all__ = [
    "GameWindow",
    "CyoaPySide6Window",
    "CliRunner",
    "Game",
    "GameSession",
    "Scenario",
    "SceneRunner",
    "Session",
    "SceneView",
    "SaveGame",
    "TurnResult",
    "create_save",
    "load_from_file",
    "load_from_slot",
    "restore_save",
    "save_to_file",
    "save_to_slot",
]
