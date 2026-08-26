from .application.startup import GameStartup
from .infrastructure.scenarios import FilesystemScenarioRepository


def main() -> None:
    from .frontends.qt.launcher import run_pyside6_app

    run_pyside6_app(GameStartup(FilesystemScenarioRepository()))


if __name__ == "__main__":
    main()
