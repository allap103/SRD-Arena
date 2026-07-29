from __future__ import annotations

import argparse
from pathlib import Path

from .content.scenarios import resolve_scenario_directory
from .frontends.cli.runner import CliRunner
from .frontends.cli.scenario_selection import select_scenario_directory
from .infrastructure.logging import (
    CHANNEL_ENGINE,
    configure_game_logging,
    get_game_logger,
)
from .runtime.game import Game
from .runtime.scenario import LoadedScenario, ScenarioLoader

LOGGER = get_game_logger(CHANNEL_ENGINE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch SRD Arena.")
    parser.add_argument(
        "scenario_dir",
        nargs="?",
        help=(
            "Scenario directory as a relative path, an absolute path, or the name of "
            "a subfolder in content/scenarios/."
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


def launch(
    *,
    frontend: str,
    scenario_dir: Path | None,
    control_mode: str = "default",
    start_scene: str | None = None,
    show_encounter_json: bool = False,
) -> None:
    match frontend:
        case "gui":
            from .frontends.qt.app import run_pyside6_app

            run_pyside6_app(
                scenario_dir=scenario_dir,
                start_scene_override=start_scene,
                control_mode=control_mode,
                show_encounter_json=show_encounter_json,
            )
        case "cli":
            if scenario_dir is None:
                scenario_dir = select_scenario_directory()
            configure_game_logging()
            scenario = ScenarioLoader().load(
                scenario_dir,
                start_scene=start_scene,
                control_mode=control_mode,
            )
            run_cli(scenario)
        case _:
            raise ValueError(f"Unsupported frontend: {frontend}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    frontend = args.frontend or "gui"
    if args.scenario_dir is not None:
        scenario_dir = resolve_scenario_directory(args.scenario_dir)
    elif frontend == "gui":
        scenario_dir = None
    else:
        scenario_dir = select_scenario_directory()
    launch(
        frontend=frontend,
        scenario_dir=scenario_dir,
        control_mode=args.control_mode,
        start_scene=args.start_scene,
        show_encounter_json=args.show_encounter_json,
    )


def run_cli(scenario: LoadedScenario) -> None:
    game = Game.start(scenario)
    runner = CliRunner()
    try:
        while runner.run(game):
            pass
    except KeyboardInterrupt, EOFError:
        LOGGER.info("You set the story aside for now. Thanks for playing.")


if __name__ == "__main__":
    main()
