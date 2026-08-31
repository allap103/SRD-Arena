# Frontend architecture

The frontends are driving adapters around the public engine and encounter-content
APIs.
The broader layering, startup flow, and public game contract are documented in
[Engine architecture](engine_architecture.md).

## GUI adapter

`frontends.gui` owns widgets, painting, pointer interaction, action menus, and
GUI-specific presentation configuration. PySide6 is its current implementation
toolkit rather than part of the adapter's public identity. `GameWindow`
receives a `GamePresenter` around an engine `Session`, plus presentation
metadata from the launcher. It does not receive an encounter directory, parse
encounter JSON, or inspect mutable domain state.

`GameWindow` is the GUI composition and orchestration shell. It wires engine
commands to three view components and owns only transient interaction state such
as the selected targeting mode and movement preview:

| Component | Responsibility |
| --- | --- |
| `ui.game_surface` | Story choices, battlefield surface, owned initiative rail, and encounter-completion overlay. |
| `ui.sidebar` | Sidebar navigation, auxiliary creature views, settings, encounter JSON, and combat log. |
| `ui.encounter.panel_renderer` | Populate encounter actions, resources, status, and allocation controls. |

The GUI may reuse the pure `domain.geometry` package for pointer-driven
area-preview rasterization. It must not import the engine or mutable encounter
implementation packages. This exception keeps one definition of grid geometry
without moving widget behavior into the engine.

## GUI presentation

`frontends.gui.presentation` turns engine observations and events into
display-ready models owned by the GUI adapter. It contains no PySide6 widgets
and imports neither engine nor domain encounter implementation. Keeping these
projections beside their sole consumer avoids suggesting that the headless
adapter shares a GUI-shaped read model.

Presentation models are frozen snapshots. Their sequences are detached into
tuples and their lookups into read-only mappings when constructed, so transient
widget changes cannot mutate the state currently being painted.

| Module | Responsibility |
| --- | --- |
| `models` | Display-ready view models. |
| `session` | Compose one presentation from a `GameObservation`. |
| `actions` | Group available and unavailable feature actions. |
| `battlefield` | Project combatants, status markers, and grid summaries. |
| `conditions` | Format effective conditions. |
| `resources` | Project turn resources, initiative, and spell slots. |
| `dice` | Turn engine `GameEvent` records into roll-log views. |

## Encounter UI

| Module | Responsibility |
| --- | --- |
| `battlefield` | Own transient pointer state, construct render input, and emit pointer-derived signals. |
| `battlefield_renderer` | Run the single ordered paint pipeline, cache content images, and return generated hit regions. |
| `battlefield_board_painter` | Paint the board, grid, team outlines, movement preview, and area geometry. |
| `battlefield_creature_painter` | Paint tokens, emphasis, names, allocation badges, and status markers while generating their hit regions. |
| `battlefield_overlay_painter` | Paint area and targeting badges plus shared floating labels and tooltips. |
| `action_menus` | Group advertised actions for menu presentation. |
| `area_previews` | Re-aim serialized area templates for the hovered cell. |
| `dice_log` | Render combat messages, dice results, and reroll controls. |
| `initiative` | Own and render the battlefield's initiative rail. |
| `status_markers` | Calculate markers, labels, tooltips, and badges. |
| `movement` | Build detached, read-only movement previews and shortest paths. |
| `targeting` | Derive target-selection modes and battlefield click actions. |
| `panel_renderer` | Render sidebar encounter controls through explicit bindings and callbacks. |
| `layout` | Clear nested GUI layouts. |
| `resource_formatting` | Format resource values for GUI labels. |

## Headless adapter

`frontends.headless.HeadlessGameAdapter` is the Python/ML-facing driving
adapter. It:

- lists encounters without exposing filesystem paths;
- starts an encounter by stable ID;
- returns typed observations and legal action IDs;
- submits direct choices or any typed engine command;
- preserves stale-decision validation;
- advances scripted controllers without owning action-selection policy.

It is intentionally not a CLI and does not load the GUI toolkit.
