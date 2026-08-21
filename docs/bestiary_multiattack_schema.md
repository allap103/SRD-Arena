# Bestiary Multiattack Schema

`mechanics` is an additive, machine-readable normalization of a stat block
entry. This document covers its `multiattack` variant. The original `entries`
value remains authoritative and must not be changed by normalization.

The canonical Pydantic models live in
`src/srd_arena/content/creatures/actions/multiattack.py`.

## Composition

A definition contains one or more alternative plans. Each plan contains:

- `steps`: invocations or repeated independent choices.
- `ordering`: `any` unless the source explicitly requires `strict` order.
- `requirement`: an optional rule controlling plan eligibility.
- `replacements`: reusable rules that substitute eligible generated slots.

Step availability is one of `required`, `optional`, or `use_if_available`.
Normal repetition uses a positive integer. Dynamic repetition supports creature
state, such as Hydra heads, and half the summoning spell's level.

## Repeated Action

```json
{
  "type": "multiattack",
  "plans": [{
    "steps": [{
      "type": "invoke",
      "invocation": {
        "type": "stat_block_action",
        "name": "Slam"
      },
      "times": 2
    }]
  }]
}
```

## Any Combination

```json
{
  "plans": [{
    "steps": [{
      "type": "choose",
      "options": [
        {"type": "stat_block_action", "name": "Scimitar"},
        {"type": "stat_block_action", "name": "Shortbow"}
      ],
      "times": 2
    }]
  }]
}
```

Each repetition makes an independent selection.

## Replacement

```json
{
  "plans": [{
    "steps": [{
      "type": "invoke",
      "invocation": {
        "type": "stat_block_action",
        "name": "Rend"
      },
      "times": 3
    }],
    "replacements": [{
      "target": {
        "type": "action",
        "name": "Rend"
      },
      "replace_count": 1,
      "maximum_uses": 1,
      "options": [
        {
          "type": "stat_block_action",
          "name": "Sleep Breath"
        },
        {
          "type": "cast_spell",
          "spell": {
            "name": "Scorching Ray",
            "source": "XPHB"
          },
          "via": "Spellcasting",
          "via_section": "spellcasting"
        }
      ]
    }]
  }]
}
```

Action names are references to existing stat-block entries. Their effects,
requirements, recharge, and availability are defined by those entries rather
than duplicated in Multiattack. Loading the containing monster validates each
reference against its declared section. Display tags on source action names,
such as recharge tags, are ignored during reference matching.
