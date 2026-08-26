from .application.startup import GameStartup


def main() -> None:
    from .frontends.qt.launcher import run_pyside6_app

    run_pyside6_app(GameStartup())


if __name__ == "__main__":
    main()
