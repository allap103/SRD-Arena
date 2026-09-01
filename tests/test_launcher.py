import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from srd_arena import main as launcher
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.rolls.randomness import DiceRoller
from srd_arena.engine.api import Session, SessionFactory


def test_main_passes_cli_seed_to_gui_encounter_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = SimpleNamespace(image_root=Path("images"))
    launched: list[tuple[object, dict[str, object]]] = []
    created_session = cast(Session, object())
    received_dice: list[DiceRoller] = []

    def _catalog() -> object:
        return catalog

    def _run_gui(received: object, **kwargs: object) -> None:
        launched.append((received, kwargs))

    def _session(
        _encounter: EncounterDefinition,
        *,
        dice: DiceRoller,
    ) -> Session:
        received_dice.append(dice)
        return created_session

    monkeypatch.setattr(launcher, "EncounterCatalog", _catalog)
    monkeypatch.setattr(launcher, "Session", _session)
    monkeypatch.setitem(
        sys.modules,
        "srd_arena.frontends.gui.launcher",
        SimpleNamespace(run_gui=_run_gui),
    )

    launcher.main(["--seed", "42"])

    assert len(launched) == 1
    assert launched[0][0] is catalog
    image_root = launched[0][1]["image_root"]
    assert isinstance(image_root, Path)
    assert image_root.name == "images"
    session_factory = cast(SessionFactory, launched[0][1]["session_factory"])
    assert session_factory(cast(EncounterDefinition, object())) is created_session
    expected_dice = DiceRoller.seeded(42)
    assert [received_dice[0].roll_die(20) for _ in range(5)] == [
        expected_dice.roll_die(20) for _ in range(5)
    ]
