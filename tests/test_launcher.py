from types import SimpleNamespace
import sys

from srd_arena import main as launcher


def test_main_launches_qt_scenario_picker(monkeypatch) -> None:
    startup = object()
    launched: list[object] = []
    monkeypatch.setattr(launcher, "GameStartup", lambda _repository: startup)
    monkeypatch.setitem(
        sys.modules,
        "srd_arena.frontends.qt.launcher",
        SimpleNamespace(
            run_pyside6_app=lambda received, **kwargs: launched.append(
                (received, kwargs)
            )
        ),
    )

    launcher.main()

    assert len(launched) == 1
    assert launched[0][0] is startup
    assert launched[0][1]["image_root"].name == "images"
