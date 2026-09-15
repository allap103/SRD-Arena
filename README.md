# SRD Arena

SRD Arena is a Python combat simulator for the 2024 rules represented by
SRD 5.2.1. It provides an interactive PySide6 GUI and a typed, frontend-neutral
application interface intended for simulations and future machine-learning
integration.

The project is under active development. Its implemented combat rules and
authored content cover only partial functionality.

## Run the application

The project uses [uv](https://docs.astral.sh/uv/) and requires Python 3.14 or
newer.

> uv sync
> uv run srd-arena

or
> uv run srd-arena --seed 42

To run the application with seed 42. 
Note that die rolls will only be the same between different executions of the same encounter if participants also perform the same steps between encounters.

## Headless observations

Run a YAML-filtered encounter without importing Qt:

```sh
uv run srd-arena --headless --encounter warlock_training --seed 42 \
  --perspective-creature warlock \
  --observation-config config/observations/player.yaml \
  --controller stdin --max-steps 1000 --max-rounds 100
```

The process displays indented JSON in terminals and emits JSON Lines to pipes
and files. Use `--output-format pretty` or `--output-format jsonl` to override
automatic detection. It accepts decision-tagged commands on stdin.
Closing stdin produces an explicit truncation result. Three supported presets
select interval, exact, or hidden enemy health. The initial policy slice uses
team perception; advanced modes fail validation until implemented. See the
[policy settings and controller protocol](config/observations/README.md) and
[replay examples](examples/headless/README.md).

## Experimental RL training

The `training` extra provides a PyTorch learner and a numerical, in-process RL
environment for overfitting one encounter. Start with the
[training instructions](config/training/README.md). To watch a saved model play:

```sh
uv run --extra training srd-arena-watch --run-dir runs/first-experiment
```

The spectator GUI has pause, single-step, restart, and playback delay controls.

## Quality checks

    uv sync --extra training --dev
    uv run --extra training pytest -q
    uv run --extra training mypy --strict .
    uv run ruff check .
    uv run ruff format --check .

## Architecture

The high-level execution path is:

    main
      -> selected frontend
      -> engine API and session
      -> encounter orchestration
      -> domain rules

Authored JSON content is validated and translated into domain definitions by
the content package. GUI and headless clients discover encounters through the
public content API and drive them through the public engine API.

`Session.observe_gameplay()` returns the shared immutable gameplay snapshot,
including unrestricted current facts and the complete recorded episode event
history. `Session.observe()` returns its legacy GUI-facing view;
`Session.observe_player(team_id)` applies team perception and remembered
knowledge to that same source. The gameplay contract is still a draft with
incomplete capability/effect descriptors; it is not a runtime checkpoint.

## Implemented player-character scope

Player-character support includes fixed Fighter examples and validated,
combat-ready Warlock and Barbarian snapshots for levels 1-5. The snapshots
resolve their selected ability scores, combat equipment, armor class, class and
subclass identity, feats, invocations or weapon masteries, known spells, and
level-dependent resources through the normal encounter loader. A recorded
selection does not imply that all of its rule effects are executable yet.

General character creation, unrestricted equipment changes, and broad class,
species, background, feat, and magic-item coverage remain outside the current
milestone. Inventory supports the combat-relevant fixed equipment and healing
potions used by authored encounters.

Monster attacks remain self-contained stat-block actions. A monster's named
weapon attack does not depend on the player-character item/loadout model.

