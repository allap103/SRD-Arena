# Observation JSON examples

Generated from the current working tree on 2026-09-13 using the real
`warlock_training` encounter and seed `42`.

- `gameplay-observation.json`: `Session.observe_gameplay()`, including current
  unrestricted facts, team perception annotations, and the complete recorded
  episode history up to this observation.
- `player-observation.json`: `Session.observe_player("heroes")` at the same
  decision point, with private enemy statistics removed and eight recent
  public events plus accumulated knowledge.
- `commands.json`: the selected external commands leading to these observations.

To reproduce the state, construct a Session from
`EncounterCatalog().load_encounter("warlock_training")` with seed 42. Before
submitting each recorded command, advance scripted actions with
`advance_player_until_input_required("heroes")` only if the player observation
reports `requires_automatic_advance`. Submit the recorded action and decision
IDs with `execute_player("heroes", SelectAction(action_id, decision_id))`.
After the final command, perform the same conditional automatic advancement.

These are complete JSON exports, with no omitted fields or abbreviated history.
The export recursively converts dataclasses to objects, mappings to objects,
tuples to arrays, enums to their values, and frozensets to sorted arrays.
Optional values remain `null`. This is an example JSON representation of the
in-process draft contract, not a versioned wire format or runtime checkpoint.

Two independent seeded executions produced identical exports. Both files were
parsed back as JSON to verify the representation.
