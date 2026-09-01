"""Compose authored content with the selected SRD Arena frontend."""

import argparse
from collections.abc import Sequence

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.rolls.randomness import DiceRoller
from srd_arena.engine.api import Session, SessionFactory


def _session_factory(seed: int | None) -> SessionFactory:
    if seed is None:
        return Session

    def create_seeded_session(encounter: EncounterDefinition) -> Session:
        return Session(encounter, dice=DiceRoller.seeded(seed))

    return create_seeded_session


def main(argv: Sequence[str] | None = None) -> None:
    """Start SRD Arena with optional reproducible encounter randomness."""

    from srd_arena.frontends.gui.launcher import run_gui

    parser = argparse.ArgumentParser(description="Run SRD Arena.")
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed encounter dice so identical decisions reproduce the same run.",
    )
    arguments = parser.parse_args(argv)
    catalog = EncounterCatalog()
    run_gui(
        catalog,
        image_root=catalog.image_root,
        session_factory=_session_factory(arguments.seed),
    )


if __name__ == "__main__":
    main()
