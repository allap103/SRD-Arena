# Application architecture

SRD Arena separates game rules, mutable execution, use cases, content loading,
and client interfaces. The application layer is the stable entry point for both
the GUI client and model-training code; neither client receives the engine
session or mutable encounter state.

## Package roles

```text
main
├── application
├── infrastructure
└── selected frontend
    ├── GUI
    └── headless

GUI/headless ──────> application
infrastructure ────> application
infrastructure ────> content
infrastructure ────> domain
content ───────────> domain
application ───────> engine
application ───────> domain
engine ────────────> domain
GUI ───────────────> domain.geometry
```

The arrows show dependencies. `main` is the composition root and chooses the
concrete filesystem and frontend adapters. Infrastructure implements the
scenario-repository port owned by the application layer and assembles domain
definitions from authored content.

| Package | Responsibility |
| --- | --- |
| `domain` | Rules, creatures, effects, geometry, capabilities, and encounter behavior. It has no dependency on application or delivery technology. |
| `engine` | Mutable game session and scene progression. It depends on domain rules and is private to the application layer. |
| `application` | Scenario source port, startup use cases, the running-game facade, observations, commands, and result translation. |
| `content` | Parse authored system and scenario data into domain definitions. |
| `infrastructure` | Implement the application scenario-source port using filesystem content. |
| `frontends.gui` | Implement the graphical client with PySide6, render observations, and translate pointer/widget input into application commands. |
| `frontends.headless` | Expose the same use cases to in-process Python and ML clients without choosing actions for them. |
| `main` | Wire `FilesystemScenarioRepository`, `GameStartup`, and the selected driving adapter. |

`application` is orchestration glue, not a parent folder for the other
packages. Content, infrastructure, and frontends are adapters around ports and
contracts owned by the application/domain core.

## Shared spatial kernel

The GUI adapter has one deliberate, narrow dependency on `domain.geometry`.
Area previews must use the same cone, line, cube, radius, rasterization, and outline
calculations as combat resolution; duplicating those rules in the frontend
could make the displayed template disagree with the affected cells.

This exception does not grant the GUI access to mutable encounter state or
combat orchestration. The geometry package is a stateless calculation kernel made of
value objects and pure operations. Pointer movement remains local presentation
behavior, so routing every transient hover position through an application
command would add ceremony without changing game state.

If spatial behavior later becomes an independently reusable subsystem—for
example when three-dimensional movement, creature footprints, cover, and line
of effect are implemented—it may be promoted to a top-level `spatial`
package shared by domain and frontend code. Until that boundary is justified
by responsibility rather than diagram symmetry, the explicit geometry
exception is preferred.

## Startup flow

```text
main
  -> FilesystemScenarioRepository
  -> GameStartup
  -> driving adapter
       -> lists ScenarioSummary values
       -> asks GameStartup to start the selected scenario
  -> repository assembles LoadedScenario from authored content
  -> GameStartup creates RunningGame around a private engine Session
  -> adapter interacts only through RunningGame
```

Scenario filesystem paths are infrastructure details. Both GUI and headless
clients select the stable IDs advertised by `GameStartup`; the filesystem
repository resolves those IDs internally. Optional board presentation metadata
is attached to the scenario summary and injected into the GUI. It never enters
the running game or engine session.

## Public game interaction

`RunningGame` exposes four categories of behavior:

1. `observe()` returns an immutable, frontend-neutral `GameObservation`.
2. `execute(command)` applies an explicit typed command and returns a
   `CommandResult` containing either a `GameUpdate` or a structured failure.
3. `advance_automatic()` runs scripted controllers until external input is
   required.
4. `reset()` returns the game to its initial observation.

An observation contains stable scenario, decision, creature, action, and
effect identifiers. Commands include the decision ID observed by the client.
If the engine has advanced since then, the application rejects the command as
stale instead of allowing an old UI or model action to affect a new decision.
Action observations expose semantic fields such as target, source, movement
direction, feature, and resource level; encoded engine action payloads remain
private to the application translator.

The command set currently covers direct selection, area aiming, staged target
changes, numeric allocations, and confirmation/cancellation. Policy remains
outside the application: the GUI waits for a user, while an ML policy chooses
among the same advertised actions.

## Read and write boundaries

```text
engine Session
    -> observation projection
    -> GameObservation / GameEvent
    -> GUI or headless client

GUI or headless client
    -> typed GameCommand + expected decision ID
    -> command validation / translation
    -> engine Session
```

The observation is a deliberate, recursively immutable public read model, not
a save format and not a copy of `EncounterState.__dict__`. Likewise,
`GameEvent` is an application-owned event record with recursively immutable
payload values; engine `CombatEvent` objects do not cross the boundary.

There is intentionally no `get_session()` or `get_encounter_state()` escape
hatch. `RunningGame` owns its session privately, and frontend dependency tests
prevent engine access from returning.

## Enforced dependency rules

- Domain imports no application, content, engine, infrastructure, or frontend.
- Engine imports domain but no application, content, infrastructure, or
  frontend.
- Application imports engine/domain contracts but no concrete content,
  infrastructure, or frontend.
- The filesystem scenario adapter may import application ports, content, and
  domain definitions.
- Shared presentation imports application contracts, not engine or encounter
  implementation packages.
- The GUI adapter imports application contracts and may reuse pure domain
  geometry for pointer-driven area rendering. It imports neither engine nor mutable
  encounter implementation packages; no other domain dependency is intended.
- The headless adapter imports application contracts only.
- Package roots do not re-export engine types and thereby hide ownership.
- Imports crossing top-level `srd_arena` packages use the full absolute path.
  Relative imports are reserved for modules within the same top-level package.

These rules are executable in `tests/test_architecture.py`.

## Deliberately deferred

- The headless adapter is an in-process Python API, not REST, a Gym environment,
  reward shaping, batching, or a training framework.
- Observation versioning and wire-format compatibility become relevant only if
  the application boundary is exposed over a process or network boundary.
- Pure GUI module-size cleanup can continue independently without changing the
  application contracts.
