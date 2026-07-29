from __future__ import annotations

import argparse
from pathlib import Path

from .content.scenarios import resolve_scenario_directory


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
    scenario_dir: Path | None,
    control_mode: str = "default",
    start_scene: str | None = None,
    show_encounter_json: bool = False,
) -> None:
    from .frontends.qt.app import run_pyside6_app

    run_pyside6_app(
        scenario_dir=scenario_dir,
        start_scene_override=start_scene,
        control_mode=control_mode,
        show_encounter_json=show_encounter_json,
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    scenario_dir = (
        resolve_scenario_directory(args.scenario_dir)
        if args.scenario_dir is not None
        else None
    )
    launch(
        scenario_dir=scenario_dir,
        control_mode=args.control_mode,
        start_scene=args.start_scene,
        show_encounter_json=args.show_encounter_json,
    )


if __name__ == "__main__":
    main()
