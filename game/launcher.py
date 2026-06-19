from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from .api.savegames import run_savegame_api
from .engine import GAME_DIR, Game
from .game_logging import configure_game_logging
from .textual_app import run_textual_app

REPO_ROOT = Path(__file__).resolve().parent.parent
ADVENTURES_DIR = REPO_ROOT / "adventures"
VALID_GAME_SUBDIRS = ("actors", "items", "scenes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the CYOA project.")
    parser.add_argument(
        "frontend",
        nargs="?",
        choices=("textual", "api", "cli"),
        default="textual",
        help="Which frontend to launch. Defaults to textual.",
    )
    parser.add_argument(
        "game",
        nargs="?",
        help=(
            "Game directory as a relative path, an absolute path, or the name of "
            "a subfolder in adventures/."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the API frontend to.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the API frontend to.",
    )
    parser.add_argument(
        "--no-popup",
        action="store_true",
        help="Run the Textual frontend in the current terminal instead of a popup.",
    )
    return parser


def resolve_game_directory(game: str | None) -> Path:
    if game is None:
        return _validate_game_directory((REPO_ROOT / GAME_DIR).resolve())

    requested = Path(game).expanduser()
    candidates = []
    if requested.is_absolute():
        candidates.append(requested)
    else:
        candidates.append((Path.cwd() / requested).resolve())
        candidates.append((ADVENTURES_DIR / game).resolve())

    for candidate in candidates:
        if candidate.exists():
            return _validate_game_directory(candidate)

    raise FileNotFoundError(
        "Could not find a game directory for "
        f"'{game}'. Tried the current working directory and adventures/."
    )


def launch(
    frontend: str,
    game_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    if frontend == "textual":
        run_textual_app(Game(str(game_dir)))
        return
    if frontend == "api":
        run_savegame_api(host=host, port=port, game_dir=game_dir)
        return

    configure_game_logging()
    Game(str(game_dir)).run()


def launch_in_new_terminal(frontend: str, game_dir: Path) -> None:
    if frontend != "textual":
        raise ValueError("Popup launch is only supported for the Textual frontend.")
    if os.name != "nt":
        raise OSError("Popup launch is currently only supported on Windows.")

    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "game.launcher",
            "--no-popup",
            "textual",
            str(game_dir),
        ],
        cwd=REPO_ROOT,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    game_dir = resolve_game_directory(args.game)
    if args.frontend == "textual" and not args.no_popup and os.name == "nt":
        launch_in_new_terminal(args.frontend, game_dir)
        return
    launch(args.frontend, game_dir, host=args.host, port=args.port)


def _validate_game_directory(path: Path) -> Path:
    if not path.is_dir():
        raise NotADirectoryError(f"'{path}' is not a directory.")

    missing = [
        subdir for subdir in VALID_GAME_SUBDIRS if not (path / subdir).is_dir()
    ]
    if missing:
        raise FileNotFoundError(
            f"'{path}' is not a valid game directory. Missing: {', '.join(missing)}."
        )
    return path


if __name__ == "__main__":
    main()
