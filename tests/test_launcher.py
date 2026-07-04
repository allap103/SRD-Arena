from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from game import main as launcher


def _make_game_dir(path: Path) -> Path:
    for subdir in ("actors", "items", "scenes"):
        (path / subdir).mkdir(parents=True, exist_ok=True)
    return path


def test_resolve_game_directory_requires_explicit_name() -> None:
    with pytest.raises(FileNotFoundError):
        launcher.resolve_game_directory(None)


def test_resolve_game_directory_accepts_relative_path(monkeypatch, tmp_path: Path) -> None:
    relative_game = _make_game_dir(tmp_path / "my_relative_game")
    monkeypatch.chdir(tmp_path)

    resolved = launcher.resolve_game_directory("my_relative_game")

    assert resolved == relative_game.resolve()


def test_resolve_game_directory_accepts_absolute_path(tmp_path: Path) -> None:
    absolute_game = _make_game_dir(tmp_path / "absolute_game")

    resolved = launcher.resolve_game_directory(str(absolute_game.resolve()))

    assert resolved == absolute_game.resolve()


def test_resolve_game_directory_accepts_scenarios_subfolder_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    adventure_game = _make_game_dir(repo_root / "app" / "content" / "scenarios" / "forest_trial")
    monkeypatch.setattr(launcher, "SCENARIOS_DIR", repo_root / "app" / "content" / "scenarios")

    resolved = launcher.resolve_game_directory("forest_trial")

    assert resolved == adventure_game.resolve()


def test_resolve_game_directory_rejects_missing_structure(tmp_path: Path) -> None:
    invalid_game = tmp_path / "broken_game"
    invalid_game.mkdir()

    with pytest.raises(FileNotFoundError):
        launcher.resolve_game_directory(str(invalid_game))


def test_launch_runs_pyside6_frontend(monkeypatch, tmp_path: Path) -> None:
    game_dir = _make_game_dir(tmp_path / "game")
    launched = []

    monkeypatch.setitem(
        sys.modules,
        "game.frontends.qt.app",
        SimpleNamespace(
            run_pyside6_app=lambda game=None, start_scene_override=None, show_encounter_json=False: launched.append(
                (
                    None if game is None else game.directory,
                    show_encounter_json,
                )
            )
        ),
    )

    launcher.launch("pyside6", game_dir, show_encounter_json=True)

    assert launched == [(game_dir, True)]


def test_main_launches_pyside6_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    game_dir = _make_game_dir(tmp_path / "game")
    launched = []

    monkeypatch.setattr(
        launcher,
        "resolve_game_directory",
        lambda game: game_dir.resolve(),
    )
    monkeypatch.setattr(launcher, "launch", lambda *args, **kwargs: launched.append(args))

    launcher.main([str(game_dir)])

    assert launched == [("pyside6", game_dir.resolve())]


def test_main_without_game_launches_picker_for_default_frontend(monkeypatch) -> None:
    launched = []

    monkeypatch.setattr(launcher, "launch", lambda *args, **kwargs: launched.append(args))

    launcher.main([])

    assert launched == [("pyside6", None)]


def test_select_game_directory_lists_available_scenarios(monkeypatch, tmp_path: Path) -> None:
    first = _make_game_dir(tmp_path / "alpha")
    _make_game_dir(tmp_path / "beta")
    monkeypatch.setattr(launcher, "SCENARIOS_DIR", tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "1")

    resolved = launcher.select_game_directory()

    assert resolved == first.resolve()


def test_parser_rejects_textual_frontend() -> None:
    parser = launcher.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--frontend", "textual"])


def test_parser_accepts_encounter_json_flag() -> None:
    parser = launcher.build_parser()

    args = parser.parse_args(["--show-encounter-json"])

    assert args.show_encounter_json is True
