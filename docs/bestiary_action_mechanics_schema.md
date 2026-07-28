# Bestiary Action Mechanics Schema

`mechanics` is an additive, machine-readable normalization of a stat-block
entry. Original `entries` remain authoritative and are never replaced.

The canonical Pydantic models live in
`src/srd_arena/content/schemas/action_mechanics.py`.

## Action Families

Non-Multiattack actions use one of four variants:

- `attack`: an attack roll followed by one or more hit effects.
- `saving_throw`: a save with success, failure, or staged-failure effects.
- `automatic`: effects applied without an attack roll or saving throw.
- `spellcasting`: a typed collection of spells the action can cast.

Multiattack remains a separate composition schema. It invokes these actions
but does not duplicate their targeting, effects, resources, or requirements.

## Shared Concepts

Targets are `self`, one or more creatures, or an area. Creature and area
targets can have typed eligibility requirements.

Effects are a discriminated union covering damage, conditions, forced
movement, speed and action-economy changes, roll modifiers, control, and
special memory acquisition. Effects may carry explicit durations.

Save failures are ordered stages. A failed repeat save advances to the next
stage when one exists; once at the last stage, further failures retain that
stage. Repeat saves state their trigger and automatic-success limit.

Action resources are either fixed uses with a reset rule or die recharge.

## Example Attack

```json
{
  "type": "attack",
  "attack_modes": ["melee"],
  "attack_bonus": 11,
  "reach_feet": 10,
  "target": {"type": "creature", "range_feet": 10},
  "hit": [
    {"type": "damage", "dice": "2d6", "bonus": 6, "damage_type": "slashing"},
    {"type": "damage", "dice": "1d8", "damage_type": "cold"}
  ]
}
```

## Example Staged Save

```json
{
  "type": "saving_throw",
  "target": {"type": "area", "shape": "cone", "size_feet": 60},
  "ability": "con",
  "dc": 20,
  "failure": [
    {
      "effects": [{
        "type": "condition",
        "condition": "incapacitated",
        "duration": {
          "type": "end_of_turn",
          "creature": "target",
          "turn_offset": 1
        }
      }],
      "repeat_saves": [{"trigger": "end_of_turn"}]
    },
    {
      "effects": [{"type": "condition", "condition": "paralyzed"}],
      "repeat_saves": [{
        "trigger": "end_of_turn",
        "automatic_success_after": {
          "type": "timed",
          "amount": 1,
          "unit": "minute"
        }
      }]
    }
  ]
}
```
