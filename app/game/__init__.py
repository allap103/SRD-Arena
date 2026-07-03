from typing import TYPE_CHECKING

from .presentation.models import SceneView, TurnResult
from .runtime.game import Game
from .runtime.save import (
    SaveGame,
    create_save,
    load_from_file,
    load_from_slot,
    restore_save,
    save_to_file,
    save_to_slot,
)
from .runtime.session import GameSession
from .story.choice_resolver import ChoiceResolver
from .story.scene_runner import SceneRunner

if TYPE_CHECKING:
    from .frontends.qt.app import CyoaPySide6Window

try:
    from .frontends.qt.app import CyoaPySide6Window
except ModuleNotFoundError:
    pass

__all__ = [
    "CyoaPySide6Window",
    "ChoiceResolver",
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
