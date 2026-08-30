"""Compose authored content with the selected SRD Arena frontend."""

from srd_arena.content.scenarios import ScenarioCatalog


def main() -> None:
    """Start the SRD Arena application."""

    from srd_arena.frontends.gui.launcher import run_gui

    catalog = ScenarioCatalog()
    run_gui(
        catalog,
        image_root=catalog.image_root,
    )


if __name__ == "__main__":
    main()
