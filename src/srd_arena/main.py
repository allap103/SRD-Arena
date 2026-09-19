"""Compose authored content with the selected SRD Arena frontend."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.engine.api import Session, SessionFactory


def _session_factory(seed: int | None) -> SessionFactory:
    if seed is None:
        return Session

    def create_seeded_session(encounter: EncounterDefinition) -> Session:
        return Session(encounter, seed=seed)

    return create_seeded_session


def main(argv: Sequence[str] | None = None) -> None:
    """Start SRD Arena with optional reproducible encounter randomness."""

    parser = argparse.ArgumentParser(description="Run SRD Arena.")
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed encounter dice so identical decisions reproduce the same run.",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--encounter")
    parser.add_argument("--perspective-creature")
    parser.add_argument("--observation-config", type=Path)
    parser.add_argument("--controller", choices=("stdin",))
    parser.add_argument(
        "--output-format",
        choices=("auto", "jsonl", "pretty"),
        default="auto",
        help="Headless output: auto uses indented JSON on terminals and JSON Lines in pipes/files.",
    )
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--max-rounds", type=int, default=100)
    arguments = parser.parse_args(argv)
    catalog = EncounterCatalog()
    if arguments.headless:
        from srd_arena.frontends.headless.cli import HeadlessSetupError, run_headless
        from srd_arena.frontends.headless.config import PolicyConfigError

        if not all(
            (
                arguments.encounter,
                arguments.perspective_creature,
                arguments.observation_config,
                arguments.controller,
            )
        ):
            parser.error(
                "--headless requires --encounter, --perspective-creature, --observation-config and --controller"
            )
        if arguments.max_steps < 1 or arguments.max_rounds < 1:
            parser.error("--max-steps and --max-rounds must be positive")
        try:
            run_headless(
                catalog=catalog,
                encounter_id=arguments.encounter,
                perspective_creature=arguments.perspective_creature,
                config_path=arguments.observation_config,
                seed=arguments.seed,
                max_steps=arguments.max_steps,
                max_rounds=arguments.max_rounds,
                stdin=sys.stdin,
                stdout=sys.stdout,
                output_format=arguments.output_format,
            )
        except (PolicyConfigError, HeadlessSetupError) as exc:
            parser.error(str(exc))
        except BrokenPipeError:
            raise SystemExit(1) from None
        except Exception:
            print("Headless runtime failure", file=sys.stderr)
            raise SystemExit(1) from None
        return
    if any(
        (
            arguments.encounter,
            arguments.perspective_creature,
            arguments.observation_config,
            arguments.controller,
            arguments.output_format != "auto",
        )
    ):
        parser.error("Controller options require --headless")
    from srd_arena.frontends.gui.launcher import run_gui

    run_gui(
        catalog,
        image_root=catalog.image_root,
        session_factory=_session_factory(arguments.seed),
    )


if __name__ == "__main__":
    main()
