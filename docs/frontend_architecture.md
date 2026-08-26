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
| `area_previews` | Re-aim serialized area templates for the hovered cell. |
| `dice_log` | Render combat messages, dice results, and reroll controls. |
| `status_markers` | Calculate markers, labels, tooltips, and badges. |
| `layout` | Clear nested Qt layouts. |
| `resource_formatting` | Format resource values for Qt labels. |

The remaining size of `frontends.qt.app` is a frontend readability concern,
not an application-boundary leak. Future extraction should move cohesive Qt
components without changing the `RunningGame` contract.

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
