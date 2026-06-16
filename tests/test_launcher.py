from pathlib import Path

import pytest

from game import launcher


def _make_game_dir(path: Path) -> Path:
    for subdir in ("actors", "items", "scenes"):
        (path / subdir).mkdir(parents=True, exist_ok=True)
    return path


def test_resolve_game_directory_uses_default_sample_game(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    sample_game = _make_game_dir(repo_root / "sample_game")
    monkeypatch.setattr(launcher, "REPO_ROOT", repo_root)
    monkeypatch.setattr(launcher, "ADVENTURES_DIR", repo_root / "adventures")
    monkeypatch.setattr(launcher, "GAME_DIR", Path("sample_game"))

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


def test_resolve_game_directory_accepts_adventures_subfolder_name(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    adventure_game = _make_game_dir(repo_root / "adventures" / "forest_trial")
    monkeypatch.setattr(launcher, "REPO_ROOT", repo_root)
    monkeypatch.setattr(launcher, "ADVENTURES_DIR", repo_root / "adventures")

    resolved = launcher.resolve_game_directory("forest_trial")

    assert resolved == adventure_game.resolve()


def test_resolve_game_directory_rejects_missing_structure(tmp_path: Path) -> None:
    invalid_game = tmp_path / "broken_game"
    invalid_game.mkdir()

    with pytest.raises(FileNotFoundError):
        launcher.resolve_game_directory(str(invalid_game))
