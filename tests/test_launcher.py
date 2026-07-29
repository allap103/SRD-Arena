from types import SimpleNamespace
import sys

from srd_arena import main as launcher


def test_main_launches_qt_scenario_picker(monkeypatch) -> None:
    launched: list[bool] = []
    monkeypatch.setitem(
        sys.modules,
        "srd_arena.frontends.qt.launcher",
        SimpleNamespace(run_pyside6_app=lambda: launched.append(True)),
    )

    launcher.main()

    assert launched == [True]
