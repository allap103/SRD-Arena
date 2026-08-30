"""Compose the production adapters and launch the SRD Arena GUI."""

from srd_arena.infrastructure.scenarios import FilesystemScenarioRepository
from srd_arena.scenarios.api import ScenarioCatalog


def main() -> None:
    """Start the SRD Arena application."""

    from srd_arena.frontends.gui.launcher import run_gui

    repository = FilesystemScenarioRepository()
    run_gui(
        ScenarioCatalog(repository),
        image_root=repository.image_root,
    )


if __name__ == "__main__":
    main()
