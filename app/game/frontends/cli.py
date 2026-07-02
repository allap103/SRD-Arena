from __future__ import annotations

import argparse
from pathlib import Path

from .api.savegames import run_savegame_api
from ..runtime.game import GAME_DIR, Game
from ..support.logging import configure_game_logging
from ..support.paths import REPO_ROOT, SCENARIOS_ROOT

SCENARIOS_DIR = SCENARIOS_ROOT
VALID_GAME_SUBDIRS = ("actors", "items", "scenes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the CYOA project.")
    parser.add_argument(
        "game",
        nargs="?",
        help=(
            "Game directory as a relative path, an absolute path, or the name of "
            "a subfolder in app/content/scenarios/."
        ),
    )
    parser.add_argument(
        "--frontend",
        choices=("pyside6", "api", "cli"),
        default="pyside6",
        help="Which frontend to launch. Defaults to pyside6.",
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
        "--control-mode",
        choices=("default", "all-user"),
        default="default",
        help="Who controls encounter teams. Defaults to content-defined controllers.",
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
        candidates.append((SCENARIOS_DIR / game).resolve())

    for candidate in candidates:
        if candidate.exists():
            return _validate_game_directory(candidate)

    raise FileNotFoundError(
        "Could not find a game directory for "
        f"'{game}'. Tried the current working directory and app/content/scenarios/."
    )


def launch(
    frontend: str,
    game_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    control_mode: str = "default",
) -> None:
    if frontend == "pyside6":
        from .qt.app import run_pyside6_app

        run_pyside6_app(Game(str(game_dir), control_mode=control_mode))
        return
    if frontend == "api":
        run_savegame_api(
            host=host,
            port=port,
            game_dir=game_dir,
            control_mode=control_mode,
        )
        return

    configure_game_logging()
    Game(str(game_dir), control_mode=control_mode).run()


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    game_dir = resolve_game_directory(args.game)
    launch(
        args.frontend,
        game_dir,
        host=args.host,
        port=args.port,
        control_mode=args.control_mode,
    )


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
