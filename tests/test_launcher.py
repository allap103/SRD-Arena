from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from srd_arena import main as launcher


def test_main_launches_gui_scenario_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    startup = object()
    launched: list[tuple[object, dict[str, object]]] = []

    def _startup(_repository: object) -> object:
        return startup

    def _run_gui(received: object, **kwargs: object) -> None:
        launched.append((received, kwargs))

    monkeypatch.setattr(launcher, "GameStartup", _startup)
    monkeypatch.setitem(
        sys.modules,
        "srd_arena.frontends.gui.launcher",
        SimpleNamespace(run_gui=_run_gui),
    )

    launcher.main()

    assert len(launched) == 1
    assert launched[0][0] is startup
    image_root = launched[0][1]["image_root"]
    assert isinstance(image_root, Path)
    assert image_root.name == "images"
