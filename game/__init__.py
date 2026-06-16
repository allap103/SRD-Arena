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
    from .textual_app import CyoaTextualApp

try:
    from .textual_app import CyoaTextualApp
except ModuleNotFoundError:
    pass

__all__ = [
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
