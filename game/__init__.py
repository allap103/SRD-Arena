from typing import TYPE_CHECKING

from .choice_resolver import ChoiceResolver
from .engine import Game
from .save import (
    SaveGame,
    create_save,
    load_from_file,
    load_from_slot,
    restore_save,
    save_to_file,
    save_to_slot,
)
from .scene_runner import SceneRunner
from .session import GameSession, SceneView, TurnResult

if TYPE_CHECKING:
    from .pyside6_app import CyoaPySide6Window
    from .textual_app import CyoaTextualApp

try:
    from .pyside6_app import CyoaPySide6Window
except ModuleNotFoundError:
    pass

try:
    from .textual_app import CyoaTextualApp
except ModuleNotFoundError:
    pass

__all__ = [
    "CyoaPySide6Window",
    "ChoiceResolver",
    "CyoaTextualApp",
    "Game",
    "GameSession",
    "SceneRunner",
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
