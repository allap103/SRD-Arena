from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from game import launcher


def _make_game_dir(path: Path) -> Path:
    for subdir in ("actors", "items", "scenes"):
        (path / subdir).mkdir(parents=True, exist_ok=True)
    return path


def test_resolve_game_directory_uses_default_sample_game(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    sample_game = _make_game_dir(repo_root / "scenarios" / "sample_game")
    monkeypatch.setattr(launcher, "REPO_ROOT", repo_root)
    monkeypatch.setattr(launcher, "SCENARIOS_DIR", repo_root / "scenarios")
    monkeypatch.setattr(launcher, "GAME_DIR", Path("scenarios") / "sample_game")

    resolved = launcher.resolve_game_directory(None)

    assert resolved == sample_game.resolve()


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
    adventure_game = _make_game_dir(repo_root / "scenarios" / "forest_trial")
    monkeypatch.setattr(launcher, "REPO_ROOT", repo_root)
    monkeypatch.setattr(launcher, "SCENARIOS_DIR", repo_root / "scenarios")

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
        "game.pyside6_app",
        SimpleNamespace(run_pyside6_app=lambda game: launched.append(game.directory)),
    )

    launcher.launch("pyside6", game_dir)

    assert launched == [game_dir]


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


def test_parser_rejects_textual_frontend() -> None:
    parser = launcher.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--frontend", "textual"])
