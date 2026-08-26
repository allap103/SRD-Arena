from types import SimpleNamespace
import sys

from srd_arena import main as launcher


def test_main_launches_qt_scenario_picker(monkeypatch) -> None:
    startup = object()
    launched: list[object] = []
    monkeypatch.setattr(launcher, "GameStartup", lambda: startup)
    monkeypatch.setitem(
        sys.modules,
        "srd_arena.frontends.qt.launcher",
        SimpleNamespace(run_pyside6_app=lambda received: launched.append(received)),
    )

    launcher.main()

    assert launched == [startup]
