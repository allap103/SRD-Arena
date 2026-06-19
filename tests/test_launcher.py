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


def test_launch_in_new_terminal_starts_textual_in_windows_console(
    monkeypatch,
    tmp_path: Path,
) -> None:
    game_dir = _make_game_dir(tmp_path / "game")
    calls = []

    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(launcher.subprocess, "CREATE_NEW_CONSOLE", 16, raising=False)
    monkeypatch.setattr(launcher.sys, "executable", "python.exe")

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)

    launcher.launch_in_new_terminal("textual", game_dir)

    assert calls == [
        (
            [
                "python.exe",
                "-m",
                "game.launcher",
                "--no-popup",
                "textual",
                str(game_dir),
            ],
            {
                "cwd": launcher.REPO_ROOT,
                "creationflags": 16,
            },
        )
    ]


def test_launch_in_new_terminal_rejects_non_textual_frontend(tmp_path: Path) -> None:
    game_dir = _make_game_dir(tmp_path / "game")

    with pytest.raises(ValueError):
        launcher.launch_in_new_terminal("api", game_dir)


def test_main_launches_textual_in_popup_by_default_on_windows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    game_dir = _make_game_dir(tmp_path / "game")
    launched = []

    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(
        launcher,
        "launch_in_new_terminal",
        lambda *args: launched.append(args),
    )

    launcher.main(["textual", str(game_dir)])

    assert launched == [("textual", game_dir.resolve())]


def test_main_no_popup_runs_textual_in_current_terminal(
    monkeypatch,
    tmp_path: Path,
) -> None:
    game_dir = _make_game_dir(tmp_path / "game")
    launched = []

    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(launcher, "launch", lambda *args, **kwargs: launched.append(args))

    launcher.main(["--no-popup", "textual", str(game_dir)])

    assert launched == [("textual", game_dir.resolve())]
