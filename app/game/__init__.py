from typing import TYPE_CHECKING

from .presentation.models import SceneView, TurnResult
from .scenarios import Scenario
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
from .story.choice_resolver import ChoiceResolver
from .frontends.cli.runner import CliRunner

Game = Scenario
GameSession = Session
SceneRunner = CliRunner

if TYPE_CHECKING:
    from .frontends.qt.app import CyoaPySide6Window

try:
    from .frontends.qt.app import CyoaPySide6Window
except ModuleNotFoundError:
    pass

__all__ = [
    "CyoaPySide6Window",
    "ChoiceResolver",
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
