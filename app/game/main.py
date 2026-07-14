from __future__ import annotations

import argparse
from pathlib import Path

from .scenarios import Scenario
from .support.logging import configure_game_logging
from .support.paths import SCENARIOS_ROOT
from .scenarios import VALID_SCENARIO_SUBDIRS, list_scenarios

SCENARIOS_DIR = SCENARIOS_ROOT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch SRD Arena.")
    parser.add_argument(
        "game_dir",
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
        choices=("gui", "cli"),
        help="Which frontend to launch. Defaults to gui when omitted.",
    )
    parser.add_argument(
        "--control-mode",
        choices=("default", "all-user"),
        default="default",
        help="Who controls encounter teams. Defaults to content-defined controllers.",
    )
    parser.add_argument(
        "--show-encounter-json",
        action="store_true",
        help="Open an additional window that shows the live encounter JSON.",
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
    *,
    frontend: str,
    game_dir: Path | None,
    control_mode: str = "default",
    start_scene: str | None = None,
    show_encounter_json: bool = False,
) -> None:
    match frontend:
        case "gui":
            from .frontends.qt.app import run_pyside6_app

            run_pyside6_app(
                scenario_dir=game_dir,
                start_scene_override=start_scene,
                control_mode=control_mode,
                show_encounter_json=show_encounter_json,
            )
        case "cli":
            if game_dir is None:
                game_dir = select_game_directory()
            configure_game_logging()
            Scenario(str(game_dir), start_scene=start_scene, control_mode=control_mode).run()
        case _:
            raise ValueError(f"Unsupported frontend: {frontend}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    frontend = args.frontend or "gui"
    if args.game_dir is not None:
        game_dir = resolve_game_directory(args.game_dir)
    elif frontend == "gui":
        game_dir = None
    else:
        game_dir = select_game_directory()
    launch(
        frontend=frontend,
        game_dir=game_dir,
        control_mode=args.control_mode,
        start_scene=args.start_scene,
        show_encounter_json=args.show_encounter_json,
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
        subdir for subdir in VALID_SCENARIO_SUBDIRS if not (path / subdir).is_dir()
    ]
    if missing:
        raise FileNotFoundError(
            f"'{path}' is not a valid game directory. Missing: {', '.join(missing)}."
        )
    return path


if __name__ == "__main__":
    main()
