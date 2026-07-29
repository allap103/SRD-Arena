from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from srd_arena import main as launcher
from srd_arena.content.scenarios import resolve_scenario_directory


def _make_scenario_dir(path: Path) -> Path:
    for subdir in ("encounters",):
        (path / subdir).mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text(
        f'{{"display_name": "{path.name.title()}"}}\n',
        encoding="utf-8",
    )
    return path


def test_resolve_scenario_directory_requires_explicit_name() -> None:
    with pytest.raises(FileNotFoundError):
        resolve_scenario_directory(None)


def test_resolve_scenario_directory_accepts_relative_path(
    monkeypatch, tmp_path: Path
) -> None:
    relative_scenario = _make_scenario_dir(tmp_path / "my_relative_scenario")
    monkeypatch.chdir(tmp_path)

    resolved = resolve_scenario_directory("my_relative_scenario")

    assert resolved == relative_scenario.resolve()


def test_resolve_scenario_directory_accepts_absolute_path(tmp_path: Path) -> None:
    absolute_scenario = _make_scenario_dir(tmp_path / "absolute_scenario")

    resolved = resolve_scenario_directory(str(absolute_scenario.resolve()))

    assert resolved == absolute_scenario.resolve()


def test_resolve_scenario_directory_accepts_scenarios_subfolder_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    adventure_scenario = _make_scenario_dir(
        repo_root / "content" / "scenarios" / "forest_trial"
    )
    resolved = resolve_scenario_directory(
        "forest_trial",
        scenarios_root=repo_root / "content" / "scenarios",
    )

    assert resolved == adventure_scenario.resolve()


def test_resolve_scenario_directory_rejects_missing_structure(tmp_path: Path) -> None:
    invalid_scenario = tmp_path / "broken_game"
    invalid_scenario.mkdir()

    with pytest.raises(FileNotFoundError):
        resolve_scenario_directory(str(invalid_scenario))


def test_launch_runs_gui_frontend(monkeypatch, tmp_path: Path) -> None:
    scenario_dir = _make_scenario_dir(tmp_path / "game")
    launched = []

    monkeypatch.setitem(
        sys.modules,
        "srd_arena.frontends.qt.app",
        SimpleNamespace(
            run_pyside6_app=lambda scenario_dir=None, start_scene_override=None, control_mode="default", show_encounter_json=False: (
                launched.append(
                    (
                        scenario_dir,
                        show_encounter_json,
                    )
                )
            )
        ),
    )

    launcher.launch(scenario_dir=scenario_dir, show_encounter_json=True)

    assert launched == [(scenario_dir, True)]


def test_main_launches_gui_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    scenario_dir = _make_scenario_dir(tmp_path / "game")
    launched = []

    monkeypatch.setattr(
        launcher,
        "resolve_scenario_directory",
        lambda scenario: scenario_dir.resolve(),
    )
    monkeypatch.setattr(
        launcher, "launch", lambda *args, **kwargs: launched.append(kwargs)
    )

    launcher.main([str(scenario_dir)])

    assert launched == [
        {
            "scenario_dir": scenario_dir.resolve(),
            "control_mode": "default",
            "start_scene": None,
            "show_encounter_json": False,
        }
    ]


def test_main_without_scenario_launches_gui_scenario_picker(
    monkeypatch,
) -> None:
    launched = []

    monkeypatch.setattr(
        launcher, "launch", lambda *args, **kwargs: launched.append(kwargs)
    )

    launcher.main([])

    assert launched == [
        {
            "scenario_dir": None,
            "control_mode": "default",
            "start_scene": None,
            "show_encounter_json": False,
        }
    ]


def test_parser_accepts_encounter_json_flag() -> None:
    parser = launcher.build_parser()

    args = parser.parse_args(["--show-encounter-json"])

    assert args.show_encounter_json is True
