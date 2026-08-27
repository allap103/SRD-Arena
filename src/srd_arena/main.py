from srd_arena.application.startup import GameStartup
from srd_arena.infrastructure.scenarios import FilesystemScenarioRepository


def main() -> None:
    from srd_arena.frontends.qt.launcher import run_pyside6_app

    repository = FilesystemScenarioRepository()
    run_pyside6_app(
        GameStartup(repository),
        image_root=repository.image_root,
    )


if __name__ == "__main__":
    main()
