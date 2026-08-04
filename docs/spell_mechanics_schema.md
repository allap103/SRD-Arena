# Executable Spell Mechanics Schema

## Purpose

The spell JSON record is the single source of truth for both its original SRD
data and its executable combat behavior. Rules prose remains available for
people, but the runtime must use the typed `mechanics` object rather than parse
`entries` or dispatch on a spell name.

The canonical Pydantic models live in
`src/srd_arena/content/schemas/spell_mechanics.py`. `SpellSchema` exposes the
two additive top-level fields described here. A machine-readable JSON Schema
can be generated from `SpellSchema.model_json_schema()`; it is not checked in,
so it cannot drift from the validating models.

## Spell record boundary

Existing spell fields continue to describe facts already encoded by the
source data:

- `level`, `school`, `time`, `range`, `components`, and `duration`;
- concentration and the spell's authored maximum duration;
- human-readable entries and higher-level text;
- useful source tags such as `savingThrow`, `damageInflict`, and
  `affectsCreatureType`.

The new fields describe implementation coverage and unambiguous executable
behavior:

```json
{
  "implementation": {
    "status": "partial",
    "scope": ["combat"],
    "omissions": [
      {
        "mechanic": "flammable object ignition",
        "reason": "Environmental fire is not modeled yet."
      }
    ]
  },
  "mechanics": {
    "target": {},
    "resolution": {},
    "casting_requirements": [],
    "casting_trigger": null,
    "scaling": [],
    "outcome_triggers": []
  }
}
```

`mechanics` deliberately does not repeat casting time, range, components, or
spell duration. The runtime reads those values from the same spell record.

## Implementation status

- `complete`: every combat-relevant branch in the declared scope is encoded.
- `partial`: executable, with every omission listed and explained.
- `unimplemented`: no executable mechanics have been authored yet.
- `blocked`: mechanics are encoded but require unavailable engine support;
  blockers must be listed.
- `out_of_scope`: intentionally excluded and accompanied by a reason.

Complete, partial, and blocked records require `mechanics`. Unimplemented and
out-of-scope records reject it. Only complete and partial records are
executable.

An independently selectable resolution branch can carry its own
implementation status. This prevents one implemented option from hiding an
unsupported option in a spell such as Eyebite.

## Mechanics structure

All polymorphic concepts are closed discriminated unions selected by `type`.
Unknown variants and unknown fields are validation errors.

### Target

Targets cover self, creatures, objects, points, event-bound targets, spell
entities, ordinary areas, constructed composite areas, and explicit choices
between target forms. Areas use typed sphere, cone, cube, line, cylinder,
emanation, wall, or ring geometry.

Requirements compose with `all` and `any` and cover conditions and their
source, creature type, size, traits, immunity, perception, willingness, free
hands, hit-point thresholds, attack properties, and spell-created
relationships.

### Resolution

The initial resolution is one of:

- automatic outcome;
- saving throw, including repeat saves and success/failure counters;
- melee or ranged spell attack;
- ability or contested check;
- HP-pool allocation;
- repeated/projectile resolution;
- ordered sequence;
- explicit choice;
- complete, non-overlapping random table.

Every branch produces an `Outcome`, which contains typed effects and can end
the parent spell instance.

### Effects

The effect union contains shared combat primitives such as damage, healing,
conditions, movement, roll modifiers, action restrictions, resistance,
immunity, and effect removal. It also contains typed orchestration primitives
for mechanics that cannot be reduced to those values alone:

- granted actions and compound modifier groups;
- persistent and moving areas;
- summons, transformations, and spell entities;
- relationships, mirrored damage, and compelled behavior;
- target interception and pending-event cancellation;
- temporary battlefield removal;
- defeat prevention;
- stored spells and accumulating dice.

These are mechanic variants, not spell-specific handlers. A runtime executor
may dispatch on `create_persistent_area`, for example, but never on
`cloudkill`.

### Lifecycle

Every applied effect retains the spell-instance identity, source, target, cast
level, and casting-stat snapshot. Unless an effect declares an earlier child
duration, it ends with its parent spell instance. Ending concentration or the
authored spell duration therefore removes all owned child conditions,
modifiers, entities, relationships, and granted actions together.

`casting_trigger` represents reaction and post-hit casting windows.
`outcome_triggers` represent later hooks such as retaliation, recurring turn
effects, damage riders, defeat interception, and on-kill behavior. Persistent
areas separately declare spatial entry and turn triggers plus a per-target
trigger limit.

### Scaling

Slot scaling is expressed as typed increments to damage dice, healing dice,
target count, projectile count, area radius, or duration. The cast level and
derived values are snapshotted on the spell instance so later granted actions
and triggers do not consume another slot or silently recalculate the original
cast.

## Example: direct area damage

```json
{
  "implementation": {
    "status": "partial",
    "omissions": [{
      "mechanic": "flammable object ignition",
      "reason": "Environmental fire is not modeled yet."
    }]
  },
  "mechanics": {
    "target": {
      "type": "area",
      "origin": "point_in_range",
      "geometry": {"shape": "sphere", "radius_feet": 20},
      "affects": "creatures_and_objects"
    },
    "resolution": {
      "type": "saving_throw",
      "ability": "dex",
      "failure": {
        "effects": [{
          "type": "damage",
          "dice": "8d6",
          "damage_type": "fire"
        }]
      },
      "success_damage": "half"
    },
    "scaling": [{
      "type": "slot_level",
      "above_level": 3,
      "per_level": [{"type": "damage_dice", "amount": "1d6"}]
    }]
  }
}
```

## Example: condition and repeat save

```json
{
  "implementation": {"status": "complete"},
  "mechanics": {
    "target": {
      "type": "creature",
      "line_of_sight": true,
      "requirements": [{
        "type": "creature_type",
        "creature_types": ["humanoid"]
      }]
    },
    "resolution": {
      "type": "saving_throw",
      "ability": "wis",
      "failure": {
        "effects": [{"type": "condition", "condition": "paralyzed"}]
      },
      "repeat_save": {"trigger": "turn_end", "ability": "wis"}
    },
    "scaling": [{
      "type": "slot_level",
      "above_level": 2,
      "per_level": [{"type": "target_count", "amount": 1}]
    }]
  }
}
```

The condition has no child duration because it is owned by the spell instance.
The record's existing `duration` field supplies the one-minute concentration
lifetime; the repeat save can end that target's spell-owned effect early.

## Spell access is separate

The definition above describes what a spell does. It does not decide how a
particular creature pays for it. Creature spell access remains a separate
policy that can select a shared spell-slot pool, an at-will grant, or limited
uses with a reset period and authored cast level. This is a resource-policy
difference, not a Player Character/NPC execution branch.

## Runtime boundary

This schema establishes representation and validation. A variant being
representable does not imply that its executor already exists. Enrichment must
therefore use `blocked` for valid mechanics awaiting engine support and
`partial` only when the encoded subset is already executable.
