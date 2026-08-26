# Frontend architecture

The frontend is an adapter around application and runtime services. It owns Qt
widgets and user interaction, but it does not construct scenarios or runtime
sessions.

## Startup sequence

```text
srd_arena.main
    -> creates GameStartup
    -> starts the Qt adapter
    -> ScenarioPickerWindow requests available scenario summaries
    -> GameStartup loads the selected scenario and creates its Session
    -> GameWindow receives the resulting RunningGame
```

`GameStartup` is the frontend-independent entry point for discovering and
starting games. A future model-training adapter can use the same service without
importing Qt.

## Responsibilities

| Component | Responsibility |
| --- | --- |
| `main` | Compose application services and select the frontend adapter. |
| `application.startup` | Discover scenarios, load the selected scenario, and create a runtime session. |
| `runtime` | Advance scenes and encounters in response to explicit decisions. |
| `frontends.qt.launcher` | Display available scenarios and forward the user's selection. |
| `frontends.qt.app` | Present a running game and translate Qt events into runtime decisions. |
| `frontends.shared` | Build frontend-neutral presentation models. |

## Shared presentation modules

| Module | Responsibility |
| --- | --- |
| `models` | Define frontend-neutral, display-ready view models. |
| `session` | Compose one session presentation from runtime state. |
| `actions` | Project available and unavailable feature actions. |
| `battlefield` | Project creatures, statuses, and grid summaries. |
| `conditions` | Extract effective condition names from serialized creature state. |
| `resources` | Project turn resources, initiative, and spell slots. |

## Encounter UI modules

| Module | Responsibility |
| --- | --- |
| `battlefield` | Draw the combat grid and translate pointer events into battlefield signals. |
| `area_previews` | Build display-ready area templates from serialized geometry and pointer positions. |
| `dice_log` | Render combat log entries, dice results, and reroll controls. |
| `status_markers` | Calculate status-marker, floating-label, and allocation-badge geometry. |
| `layout` | Provide recursive Qt layout cleanup. |
| `resource_formatting` | Format resource values for Qt labels. |

The package exports its public widgets from `frontends.qt.ui.encounter`; callers
do not depend on the implementation modules directly.

## Dependency rule

The application and runtime packages must not import a frontend. Frontends may
depend on the application boundary, shared presentation models, and runtime
interfaces. This direction is enforced by the architecture tests.

## Refactor constraints

- Preserve visible behavior while reorganizing the frontend.
- Move complete responsibilities in small commits.
- Keep game rules out of Qt event handlers and painting code.
- Prefer pure geometry and presentation helpers where ordinary unit tests are
  sufficient.
- Use Qt-focused tests for signal wiring, event handling, and painting behavior.
