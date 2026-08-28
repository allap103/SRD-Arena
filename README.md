# SRD Arena

SRD Arena is a Python combat simulator for the 2024 rules represented by
SRD 5.2. It provides an interactive PySide6 GUI and a typed, frontend-neutral
application interface intended for simulations and future machine-learning
integration.

The project is under active development. Its implemented combat rules and
authored content cover only the functionality described by the repository's
tests and documentation.

## Run the application

The project uses [uv](https://docs.astral.sh/uv/) and requires Python 3.14 or
newer.

    uv sync
    uv run srd-arena

## Quality checks

    uv run pytest -q
    uv run mypy --strict .
    uv run ruff check .
    uv run ruff format --check .

## Architecture

The high-level execution path is:

    main
      -> application use cases
      -> engine session
      -> encounter orchestration
      -> domain rules

Authored JSON content is validated and translated into domain definitions by
the content package. Infrastructure connects that content to the application,
while GUI and headless clients drive the same public application API.

See the
[application architecture](docs/application_architecture.md),
[combat action architecture](docs/combat_action_architecture.md), and
[documentation index](docs/index.md) for the detailed design.

## Documentation

Build the Sphinx documentation locally with:

    uv run sphinx-build -b html docs build/docs

The documentation combines architecture notes, content-schema references, API
documentation, and executable examples from the project's docstrings.
