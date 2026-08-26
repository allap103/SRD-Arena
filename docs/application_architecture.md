# Application architecture

SRD Arena separates game rules, mutable execution, use cases, content loading,
and client interfaces. The application layer is the stable entry point for both
the Qt client and model-training code; neither client receives the engine
session or mutable encounter state.

## Package roles

```text
                            main
                             |
                    composition / wiring
                      /              \
        filesystem scenario adapter   driving adapter
                 |                    /           \
              content               Qt         headless
                 |                    \           /
                 v                     application
              domain                /             \
                                   runtime ------> domain
```

The arrows show dependencies. `main` is the composition root and chooses the
concrete filesystem and frontend adapters.

| Package | Responsibility |
| --- | --- |
| `domain` | Rules, creatures, effects, geometry, capabilities, and encounter behavior. It has no dependency on application or delivery technology. |
| `runtime` | Mutable engine session and scene progression. It depends on domain rules and is private to the application layer. |
| `application` | Scenario source port, startup use cases, the running-game facade, observations, commands, and result translation. |
| `content` | Parse authored system and scenario data into domain definitions. |
| `infrastructure` | Implement the application scenario-source port using filesystem content. |
| `frontends.qt` | Render observations and translate pointer/widget input into application commands. |
| `frontends.headless` | Expose the same use cases to in-process Python and ML clients without choosing actions for them. |
| `main` | Wire `FilesystemScenarioRepository`, `GameStartup`, and the selected driving adapter. |

`application` is orchestration glue, not a parent folder for the other
packages. Content, infrastructure, and frontends are adapters around ports and
contracts owned by the application/domain core.

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

Scenario filesystem paths are composition details. The headless adapter maps
public scenario IDs back to the summaries advertised by `GameStartup`, so a
model does not need to know the content layout.

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
outside the application: Qt waits for a user, while an ML policy chooses among
the same advertised actions.

## Read and write boundaries

```text
engine Session
    -> observation projection
    -> GameObservation / GameEvent
    -> Qt or headless client

Qt or headless client
    -> typed GameCommand + expected decision ID
    -> command validation / translation
    -> engine Session
```

The observation is a deliberate public read model, not a save format and not a
copy of `EncounterState.__dict__`. Likewise, `GameEvent` is an application-owned
event record; engine `CombatEvent` objects do not cross the boundary.

There is intentionally no `get_session()` or `get_encounter_state()` escape
hatch. `RunningGame` owns its session privately, and frontend dependency tests
prevent runtime access from returning.

## Enforced dependency rules

- Domain imports no application, content, infrastructure, runtime, or frontend.
- Runtime imports domain but no application, content, infrastructure, or
  frontend.
- Application imports runtime/domain contracts but no concrete content,
  infrastructure, or frontend.
- The filesystem scenario adapter may import application ports, content, and
  domain definitions.
- Shared presentation imports application contracts, not runtime or encounter
  implementation packages.
- Qt imports application contracts and may reuse pure domain geometry for
  pointer-driven area rendering; it imports neither runtime nor encounter
  implementation packages.
- The headless adapter imports application contracts only.
- Package roots do not re-export engine types and thereby hide ownership.

These rules are executable in `tests/test_architecture.py`.

## Deliberately deferred

- Renaming `runtime` to `engine` is cosmetic and should be considered
  separately.
- The headless adapter is an in-process Python API, not REST, a Gym environment,
  reward shaping, batching, or a training framework.
- Observation versioning and wire-format compatibility become relevant only if
  the application boundary is exposed over a process or network boundary.
- Pure Qt module-size cleanup can continue independently without changing the
  application contracts.
