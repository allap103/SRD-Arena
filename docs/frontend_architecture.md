# Frontend architecture

The frontends are driving adapters around the application API. The broader
layering, startup flow, and public game contract are documented in
[Application architecture](application_architecture.md).

## Qt adapter

`frontends.qt` owns widgets, painting, pointer interaction, action menus, and
Qt-specific presentation configuration. `GameWindow` receives a `RunningGame`
plus presentation metadata from the launcher and interacts through application
observations and commands. It does not receive a scenario directory, parse
scenario JSON, or inspect the engine session.

`GameWindow` is the Qt composition and orchestration shell. It wires application
commands to three view components and owns only transient interaction state such
as the selected targeting mode and movement preview:

| Component | Responsibility |
| --- | --- |
| `ui.game_surface` | Story choices, battlefield surface, owned initiative rail, and encounter transition overlay. |
| `ui.sidebar` | Sidebar navigation, auxiliary creature views, settings, encounter JSON, and combat log. |
| `ui.encounter.panel_renderer` | Populate encounter actions, resources, status, and allocation controls. |

Qt may reuse the pure `domain.geometry` package for pointer-driven area-preview
rasterization. It must not import runtime or mutable encounter implementation
packages. This exception keeps one definition of grid geometry without moving
widget behavior into the application layer.

## Shared presentation

`frontends.shared` turns application observations and events into display-ready
models used by Qt. It contains no Qt widgets and imports neither runtime nor
domain encounter implementation.

| Module | Responsibility |
| --- | --- |
| `models` | Display-ready view models. |
| `session` | Compose one presentation from a `GameObservation`. |
| `actions` | Group available and unavailable feature actions. |
| `battlefield` | Project combatants, status markers, and grid summaries. |
| `conditions` | Format effective conditions. |
| `resources` | Project turn resources, initiative, and spell slots. |
| `dice` | Turn application `GameEvent` records into roll-log views. |

## Encounter UI

| Module | Responsibility |
| --- | --- |
| `battlefield` | Draw the combat grid and emit pointer-derived signals. |
| `action_menus` | Group advertised actions for menu presentation. |
| `area_previews` | Re-aim serialized area templates for the hovered cell. |
| `dice_log` | Render combat messages, dice results, and reroll controls. |
| `initiative` | Own and render the battlefield's initiative rail. |
| `status_markers` | Calculate markers, labels, tooltips, and badges. |
| `movement` | Build immutable movement-preview ownership and shortest paths. |
| `targeting` | Derive target-selection modes and battlefield click actions. |
| `panel_renderer` | Render sidebar encounter controls through explicit bindings and callbacks. |
| `layout` | Clear nested Qt layouts. |
| `resource_formatting` | Format resource values for Qt labels. |

## Headless adapter

`frontends.headless.HeadlessGameAdapter` is the Python/ML-facing driving
adapter. It:

- lists scenarios without exposing filesystem paths;
- starts a scenario by stable ID;
- returns typed observations and legal action IDs;
- submits direct choices or any typed application command;
- preserves stale-decision validation;
- advances scripted controllers without owning action-selection policy.

It is intentionally not a CLI and does not load Qt.
