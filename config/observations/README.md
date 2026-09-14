# YAML observation policies

The headless CLI implements the first slice of policy schema version 1. Every
policy must supply the complete explicit shape shown in `player.yaml`. Unknown
keys, missing fields, coercions, and valid-but-unimplemented modes are errors.
The larger proposed schema in `.agents` remains a roadmap.

## Launch

```sh
uv run srd-arena --headless \
  --encounter warlock_training --seed 42 \
  --perspective-creature warlock \
  --observation-config config/observations/player.yaml \
  --controller stdin --max-steps 1000 --max-rounds 100
```

`player.yaml` exposes enemy HP intervals; `visible-health.yaml` exposes exact
HP for perceived enemies; `hidden-health.yaml` omits enemy HP. All three use
team perception and remember previously disclosed facts when enemies leave
view. `own` always means the selected creature, including during allied turns
and interrupt decisions. The controller responds for external decisions on
that creature's team; other teams must have scripted controllers.

These are minimal experimental profiles, not a complete training feature set.
Legacy `Session.observe_player(team_id)` remains unchanged. The new engine API
is `PolicyProjector(policy, perspective_creature_ref).project(gameplay_snapshot)`.
A projector belongs to one policy and perspective for its lifetime. Feed it each
step's snapshot in order. Episode changes reset memory. Engine-owned policies
are frozen Pydantic records; YAML/file handling stays in the headless frontend.

## Supported settings

| Setting | Implemented modes |
| --- | --- |
| Knowledge sharing | `team` |
| Visibility | Own/ally `always`; enemy `perceived` |
| Dynamic memory | Own/ally `current_only`; enemy `current_only` or `last_known` |
| Demonstrated memory | `retain`, with both demonstrated accumulation flags `false` |
| Position, size, appearance | `exact`, `exact`, `visible_equipment` respectively |
| Creature type | `apparent` |
| Health | Own/ally `exact`; enemy `exact`, `interval`, `hidden` |
| Temporary health | Own/ally `exact`; enemy `exact`, `presence`, `hidden` |
| Defeated | `include` or `omit`, independently by group |
| Armor class | Own/ally `exact`; enemy `hidden` |
| Ability/save/skill fields, movement, action economy, resources | `hidden` |
| Capabilities, defenses, conditions, effects (including details), relationships | `hidden` |
| Board dimensions, terrain | `include`, `all` respectively |
| Environment | `all` (currently sunlight) or `hidden` |
| Persistent areas | `hidden` |
| Round, active turn | `include` or `omit` |
| Initiative | `order` or `hidden` |
| Roster | `all` |
| Recent events | `perceived` or `hidden`; limit 0–10000 |
| Accumulated damage received | `exact` or `hidden`, independently by group |
| Decision context | `permitted` or `hidden` |
| Capability descriptions | `hidden` |

Exact allied HP is required because existing targeting allocation limits can
reveal missing allied HP. Additional modes require consistent source evidence,
command validation and disclosure; they are rejected rather than approximated.
Individual perception, explored terrain, detailed effects and demonstrated
capability/defense descriptors remain unimplemented.

Health intervals carry only fractional bounds and endpoint flags. Positive
intervals use `(lower, upper]`; zero is `[0, 0]`. With
`distinguish_full_health: true`, full health is `[1, 1]` and the last positive
interval excludes 1. Temporary HP is separate. `hidden` yields null, never zero.
A stale row carries its last admitted value, not the current hidden value.

`filtered-observation-v1` has a fixed layout for the supported slice. Properties
whose only supported mode is `hidden` have no output field. Supported optional
fields use null when hidden/unknown; `knowledge` distinguishes current,
last-known and unknown creature rows. Resolved policy metadata distinguishes
hidden fields from unknown values. Health has nullable `current`, `maximum`,
and `interval` members, with only the selected representation populated.

Recent events use emission-time visibility, independent numbering after
filtering, and configurable retention. The current conservative event vocabulary
is attacks, retaliation, stat-block actions, spell use, feature/item use,
movement and defeat. Conditions/effect records and capability source IDs are
suppressed in this slice. Event damage is separately permitted evidence even
when HP is hidden; accumulated damage can remain enabled when the recent event
window is hidden. These controls do not prevent inference from permitted facts.

Mandatory action IDs, kinds, actor/target references, availability and required
configuration remain available. IDs are opaque command tokens. Optional labels,
reasons, costs and previews are omitted. Targeting uses the existing team-safe
projection; the YAML does not alter combat rules or visibility for targeting.

## JSON Lines protocol (version 1)

Output defaults to `--output-format auto`: terminals display indented JSON
with blank lines between records; pipes and redirected files retain compact
JSON Lines. Use `--output-format pretty` to force readable JSON (including in
an IDE console), or `--output-format jsonl` to force the controller protocol.
Formatting preserves all fields and values, including nulls and metadata.
Stdin commands remain one JSON record per line in every output mode.

For example, append `--output-format pretty` to the launch command above.
Pretty output contains multiline JSON objects and is not a JSON Lines stream.
Each record is flushed immediately. Stderr contains setup/runtime diagnostics.
Records are:

- `metadata`: package/source/output/policy versions, SHA-256 of canonical resolved
  policy, resolved settings, encounter, seed, fixed perspective and limits.
- `observation`: `observation` contains the filtered engine record at external
  decisions and at termination/limit truncation. Automatic actions advance one
  at a time; memory consumes their snapshots even when no line is emitted.
- `error`: recoverable malformed/stale/rejected command; no private engine
  messages. The next observation re-advertises current options.
- `result`: terminated/truncated flags, separate reasons, winner and step count.

Write commands to stdin using the latest decision ID and an advertised action:

```json
{"type":"command","command":"select_action","action_id":"initiative-swap-warlock-keep","expected_decision_id":"REPLACE_WITH_OBSERVED_ID"}
```

Every command has `type`, `command`, `expected_decision_id`. Payloads are:

| `command` | Additional fields |
| --- | --- |
| `select_action` | `action_id` |
| `aim_action` | `action_id`, numeric `x`, numeric `y` |
| `change_target` | `target_ref`, boolean `remove`, optional `source_trigger_id` |
| `set_resource_allocation` | `target_ref`, integer `amount` |
| `confirm_targeting` | None |
| `cancel_targeting` | None |

A step is one accepted external command or one automatic action. Rejections
consume no steps. A round limit of N permits rounds 1 through N and truncates
on entry to N+1, using the internal clock even when the policy omits it.
Termination takes precedence over limits. EOF truncates with
`controller_input_ended`; it never invents a winner. Stdin blocks while awaiting
input; there is no implicit timeout. An external decision on another team is a
runtime error because this driver has only one team controller.

Exit 0 means a completed stream (including ordinary truncation/rejections),
exit 2 means invalid setup/configuration, and exit 1 means unexpected runtime or
output failure. Version identifiers are not a cross-version replay guarantee.

Files are limited to 65536 bytes and nesting depth 16. Interval boundaries are
limited to 1024 entries. YAML anchors/aliases, merge keys, explicit tags,
duplicate/non-string keys, multiple documents and nonfinite numbers are rejected.
The command limit is 65536 characters per line; oversized records are drained
before continuing. There is no config inheritance or interpolation. Comments
and mapping order do not affect the policy digest; names do.
