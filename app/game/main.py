from __future__ import annotations

import argparse
from pathlib import Path

from .frontends.api.savegames import run_savegame_api
from .runtime.game import GAME_DIR, Game
from .support.logging import configure_game_logging
from .support.paths import REPO_ROOT, SCENARIOS_ROOT
from .support.scenarios import VALID_GAME_SUBDIRS, list_scenarios

SCENARIOS_DIR = SCENARIOS_ROOT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch SRD Arena.")
    parser.add_argument(
        "game",
        nargs="?",
        help=(
            "Game directory as a relative path, an absolute path, or the name of "
            "a subfolder in app/content/scenarios/."
        ),
    )
    parser.add_argument(
        "--start-scene",
        help="Override the scenario start scene.",
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
        raise FileNotFoundError("No game directory provided.")

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
    game_dir: Path | None,
    host: str = "127.0.0.1",
    port: int = 8000,
    control_mode: str = "default",
    start_scene: str | None = None,
) -> None:
    if frontend == "pyside6":
        from .frontends.qt.app import run_pyside6_app

        game = (
            Game(str(game_dir), start_scene=start_scene, control_mode=control_mode)
            if game_dir is not None
            else None
        )
        run_pyside6_app(game=game, start_scene_override=start_scene)
        return
    if game_dir is None:
        game_dir = select_game_directory()
    if frontend == "api":
        run_savegame_api(
            host=host,
            port=port,
            game_dir=game_dir,
            control_mode=control_mode,
            start_scene=start_scene,
        )
        return

    configure_game_logging()
    Game(str(game_dir), start_scene=start_scene, control_mode=control_mode).run()


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    game_dir = None if args.game is None and args.frontend == "pyside6" else (
        resolve_game_directory(args.game) if args.game is not None else select_game_directory()
    )
    launch(
        args.frontend,
        game_dir,
        host=args.host,
        port=args.port,
        control_mode=args.control_mode,
        start_scene=args.start_scene,
    )


def select_game_directory() -> Path:
    scenarios = list_scenarios(SCENARIOS_DIR)
    if not scenarios:
        raise FileNotFoundError("No scenarios are available in app/content/scenarios/.")
    print("Available scenarios:")
    for index, scenario in enumerate(scenarios, start=1):
        print(f"{index}. {scenario.label} ({scenario.id})")
    while True:
        choice = input("Choose a scenario: ")
        try:
            selected_index = int(choice) - 1
        except ValueError:
            print("Please enter a valid number.")
            continue
        if 0 <= selected_index < len(scenarios):
            return scenarios[selected_index].directory
        print("Please choose one of the listed scenarios.")


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
