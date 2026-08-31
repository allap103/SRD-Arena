# Engine architecture

SRD Arena separates reusable rules, one running game's mutable state, encounter
discovery, authored-content loading, and client presentation. There is no
separate `application` package: it duplicated an input/output boundary that is
already a natural responsibility of the engine.

The engine exposes the frontend-neutral game API itself. It accepts typed
commands, validates them against the current decision, advances domain state,
and projects immutable observations. It does not know about widgets, timers,
files, or presentation-specific view models.

## Package roles

```text
main
├── content ────────> domain
├── engine ─────────> domain
└── selected frontend
    ├── GUI ────────> engine.api + content.encounters
    └── headless ───> engine.api + content.encounters
```

The arrows show dependencies. `main` is the composition root. It creates the
authored `EncounterCatalog` and passes it to the selected frontend.

| Package | Responsibility |
| --- | --- |
| `domain` | Rules and definitions for encounters, creatures, effects, geometry, and capabilities. |
| `engine` | Mutable session execution plus the commands, validation, events, and immutable observations used to drive it. |
| `content` | Validate authored system and encounter files and build domain definitions. |
| `frontends.gui` | Implement the graphical client with a Qt-independent presenter and PySide6 views. |
| `frontends.headless` | Expose the engine API to in-process Python and ML clients without choosing actions for them. |
| `main` | Create `EncounterCatalog` and launch the selected frontend. |

Encounter content follows the domain/content split. `domain.encounters` defines
one complete encounter and the templates it references; `content.encounters`
discovers and validates authored files. `Session` accepts a domain
`EncounterDefinition` and owns only its mutable execution.

## Domain rule-query boundary

`EncounterState` remains the mutable encounter aggregate. Stateless rule
queries live as focused functions under `domain.encounters.rule_queries`.
Their small structural contexts expose only the state each calculation needs,
so reusable calculations remain independent of initiative, decision stacks,
and encounter orchestration.

## Spell-resolution boundary

A spell choice is represented by a typed `SpellActionPayload`. Target
references, aim points, slot level, selectable effects, and resource
allocations are named fields rather than fragments encoded into a string. The
payload is serialized only when combat events cross the observation boundary.

The source-neutral spell resolver receives a frozen `SpellActionContext` with
read-only invocation and target facts. Operations that must remain live—dice,
effect-aware modifiers, health changes, and spatial targeting—cross the narrow
`SpellResolutionEnvironment` protocol. Spell code therefore does not depend on
the entire mutable encounter aggregate.

## GUI interaction split

The GUI launcher wraps each `Session` in a `GamePresenter` before constructing
the PySide6 window:

```text
Qt signal -> GameWindow -> GamePresenter -> Session
                                      <- GameUpdate / GameObservation
          <- render refreshed presentation
```

`GamePresenter` owns the latest immutable observation, command construction,
stale decision identifiers, rejected-command refreshes, and automatic-
advancement requests. It also owns staged targeting modes. It imports no
PySide6 modules and is tested without a widget tree. `GameWindow` owns
rendering, timers, and other transient GUI state.

This is a pragmatic MVP split: `engine.api` is the public model boundary, the
presenter coordinates it for this adapter, and the widgets form the view.

## Shared spatial kernel

The GUI has one deliberate, narrow dependency on `domain.geometry`. Area
previews must use the same cone, line, cube, radius, rasterization, and outline
calculations as combat resolution. This stateless calculation package exposes
no mutable encounter state.

## Startup flow

```text
main
  -> EncounterCatalog
  -> driving adapter
       -> lists EncounterSummary values
       -> asks EncounterCatalog to load the selected encounter
  -> catalog assembles a domain EncounterDefinition
  -> adapter creates an engine Session from that definition
  -> adapter interacts with Session through engine.api
```

Encounter paths are content-loading details. GUI and headless clients select
the stable IDs advertised by `EncounterCatalog`; the catalog resolves those IDs
internally. Optional board presentation metadata is attached
to `EncounterSummary` and never enters the engine session.

## Public game interaction

`srd_arena.engine.api` is the supported in-process game interface for driving
adapters. `srd_arena.content.encounters` is the corresponding authored-encounter
interface.
Their implementation modules are not frontend extension points.

`Session` exposes five categories of behavior:

1. `observe()` returns an immutable, frontend-neutral `GameObservation`.
2. `execute(command)` applies a typed command and returns either a `GameUpdate`
   or a structured failure.
3. `advance_one_automatic_action()` resolves one scripted action immediately,
   allowing a presentation client to schedule the next step.
4. `advance_until_input_required()` resolves scripted controllers immediately
   until an external decision is required.
5. `reset()` restores the game and returns its initial observation.

Commands contain the decision ID observed by the client. If the engine has
advanced since then, it rejects the command as stale instead of allowing old
GUI or model input to affect a new decision. Policy remains outside the engine:
the GUI waits for a user while an ML policy chooses among the same advertised
actions.

Command handling and observation projection depend internally on a narrow
structural `GameEngine` protocol. The public `Session` implements that protocol
and owns concrete domain state. Its constructor accepts a domain
`EncounterDefinition`; content never imports the engine.

## Read and write boundaries

```text
engine Session/domain state
    -> internal SessionRead / ActionOption
    -> engine observation projection
    -> GameObservation / GameEvent
    -> GUI or headless client

GUI or headless client
    -> typed GameCommand + expected decision ID
    -> engine validation
    -> typed selection / action configuration
    -> domain execution through Session
    -> minimal internal EngineOutcome
    -> fresh GameObservation
```

The observation is a recursively immutable public read model, not a save format
or a copy of `EncounterState.__dict__`. `GameEvent` likewise contains detached,
immutable payload values rather than domain `CombatEvent` objects. These
transport-shaped values are not yet a versioned wire protocol.

`SessionRead` is an internal query result, not a second client model. It carries
normalized action candidates and briefly borrows an encounter-state reference
while observation projection runs. `EngineOutcome` contains only facts emitted
by an operation, such as messages, events, and lifecycle flags.

## Enforced dependency rules

- Domain imports no content, engine, infrastructure, or frontend.
- Content imports domain definitions but no engine or frontend.
- Engine imports domain but no content, infrastructure, or frontend.
- Driving adapters import game contracts through `srd_arena.engine.api` and
  authored encounter contracts through `srd_arena.content.encounters`.
- GUI presentation imports the public engine API, not engine implementation or
  encounter implementation packages.
- The GUI may reuse pure domain geometry but no mutable domain state.
- The headless adapter imports only the public engine and encounter-content APIs.
- Top-level package roots do not re-export types and hide their ownership.
- Imports crossing top-level `srd_arena` packages are absolute.

These rules are executable in `tests/test_architecture.py`.

## Deliberately deferred

- The headless adapter is an in-process Python API, not REST, a Gym environment,
  reward shaping, batching, or a training framework.
- Observation versioning matters only if the engine API crosses a process or
  network boundary.
- GUI module-size cleanup can continue independently of engine contracts.
