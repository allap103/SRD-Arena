import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from srd_arena import main as launcher


def test_main_launches_gui_encounter_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = SimpleNamespace(image_root=Path("images"))
    launched: list[tuple[object, dict[str, object]]] = []

    def _catalog() -> object:
        return catalog

    def _run_gui(received: object, **kwargs: object) -> None:
        launched.append((received, kwargs))

    monkeypatch.setattr(launcher, "EncounterCatalog", _catalog)
    monkeypatch.setitem(
        sys.modules,
        "srd_arena.frontends.gui.launcher",
        SimpleNamespace(run_gui=_run_gui),
    )

    launcher.main()

    assert len(launched) == 1
    assert launched[0][0] is catalog
    image_root = launched[0][1]["image_root"]
    assert isinstance(image_root, Path)
    assert image_root.name == "images"
