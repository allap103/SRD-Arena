# Capability and Effect System Design

## Context

The current combat feature path started with Fighter's Second Wind. That works for a single class feature, but the game will eventually need action-like abilities from many sources:

- Class features
- Feats
- Backgrounds
- Species traits
- Items
- Monster stat blocks and special attacks

Many of those abilities will also resolve into more than one outcome. For example, a monster bite might deal piercing damage, then poison the target on a failed save. A class feature might heal and remove a condition. An item might deal damage and push a target.

The runtime should not need a bespoke top-level event field or one-off resolver shape for every combination.

## Goals

- Represent player, NPC, monster, and item abilities through a shared runtime model.
- Allow one action to produce multiple ordered effects.
- Keep source-specific parsing separate from runtime resolution.
- Make common mechanics data-driven where reasonable.
- Preserve custom resolvers for genuinely unique abilities.
- Keep encounter code focused on turn flow, action economy, targeting, and event emission.

## Non-Goals

- Fully modeling every D&D feature immediately.
- Removing all custom Python resolvers.
- Replacing the existing attack system in one step.
- Designing the final UI presentation model for every effect type.

## Core Concepts

### Capability

A capability is anything an actor or item grants that can affect play. It may be active, passive, triggered, or usable as a special attack.

```python
@dataclass
class Capability:
    id: str
    name: str
    source_type: str  # class, feat, background, species, item, monster
    source_id: str
    action_type: str  # action, bonus_action, reaction, passive, triggered, special_attack
    resolver: str
    data: dict[str, object]
    cost: dict[str, int] = field(default_factory=dict)
    uses: ResourceDefinition | None = None
    targeting: TargetingDefinition | None = None
```

At runtime, encounter logic should mostly care about `action_type`, `cost`, `uses`, `targeting`, and `resolver`. The source tells us where the capability came from, but not necessarily how it resolves.

### Effect Result

An effect result is one concrete outcome produced by resolving a capability.

```python
@dataclass
class EffectResult:
    kind: str  # damage, healing, condition, movement, resource, message
    target_ref: str
    success: bool = True
    data: dict[str, object] = field(default_factory=dict)
```

Examples:

```python
EffectResult(
    kind="damage",
    target_ref="enemy:0",
    data={
        "amount": 7,
        "damage_type": "poison",
        "roll": {"dice": "2d6", "dice_total": 7},
    },
)

EffectResult(
    kind="condition",
    target_ref="player",
    data={
        "condition": "poisoned",
        "duration": "1 minute",
        "save_dc": 13,
    },
)
```

### Capability Action Result

A capability action result is the full outcome of resolving one capability use.

```python
@dataclass
class CapabilityActionResult:
    capability_id: str
    capability_name: str
    messages: list[tuple[str, str]]
    effects: list[EffectResult]
    resource_updates: dict[str, int] = field(default_factory=dict)
```

Second Wind becomes a one-effect action:

```python
CapabilityActionResult(
    capability_id="second_wind",
    capability_name="Second Wind",
    messages=[...],
    effects=[
        EffectResult(
            kind="healing",
            target_ref="player",
            data={
                "amount": 7,
                "roll": {"dice": "1d10", "dice_total": 5, "modifier": 2},
            },
        )
    ],
)
```

A damage plus debuff attack becomes a two-effect action:

```python
CapabilityActionResult(
    capability_id="venomous_bite",
    capability_name="Venomous Bite",
    messages=[...],
    effects=[
        EffectResult(kind="damage", target_ref="player", data={...}),
        EffectResult(kind="condition", target_ref="player", data={...}),
    ],
)
```

## Source Normalization

Different content sources should normalize into capabilities before combat runtime sees them.

Suggested source modules:

```text
game/capabilities/
  types.py
  registry.py
  resolvers/
    healing.py
    damage.py
    conditions.py
    custom/
      fighter.py
      monsters.py
  sources/
    classes.py
    feats.py
    backgrounds.py
    species.py
    items.py
    monsters.py
```

Source modules answer: "What capabilities does this content grant?"

Resolvers answer: "What happens when this capability is used?"

For example, Fighter data can normalize Second Wind into:

```python
Capability(
    id="second_wind",
    name="Second Wind",
    source_type="class",
    source_id="fighter",
    action_type="bonus_action",
    resolver="healing.self",
    cost={"bonus_action": 1},
    data={
        "dice": "1d10",
        "modifier": "actor.level",
    },
)
```

The same `healing.self` resolver could also support potions, species traits, and magic items.

## Resolver Strategy

Prefer generic resolvers for common mechanics:

- `healing.self`
- `healing.target`
- `damage.roll`
- `attack.weapon`
- `attack.natural`
- `condition.apply`
- `movement.push`
- `resource.restore`
- `save.then_effects`

Use custom resolvers when a feature has unusual control flow or highly specific rules.

Custom resolvers should still return `CapabilityActionResult` with structured `EffectResult` entries. That keeps the rest of the engine and UI consistent.

## Event Shape

Combat events should eventually move away from top-level fields like `healing`, `healing_roll_detail`, or custom one-off payloads. A capability event can carry the ordered effect list:

```python
{
    "kind": "capability",
    "capability_id": "venomous_bite",
    "capability_name": "Venomous Bite",
    "source_type": "monster",
    "source_id": "giant_spider",
    "success": True,
    "effects": [
        {"kind": "damage", "target_ref": "player", "data": {...}},
        {"kind": "condition", "target_ref": "player", "data": {...}},
    ],
}
```

Presentation can then render the effect list in order, while save games and logs keep a stable, inspectable structure.

## Resource and Rest Model

Capabilities should declare their resources independently of source:

```python
@dataclass
class ResourceDefinition:
    key: str
    max_uses: int
    recharge: dict[str, int | str]  # short_rest, long_rest, round, turn
```

The current rest code already has the right general idea: restore resources based on recharge metadata. Long term, `feature_uses_remaining` can become a more general `resource_uses_remaining`.

## Migration Plan

1. Keep the current `FeatureGrant` path working.
2. Introduce `Capability`, `EffectResult`, and `CapabilityActionResult` alongside existing feature types.
3. Convert Second Wind internally to return `CapabilityActionResult` effects while preserving the existing event payload for compatibility.
4. Add a generic `healing.self` resolver and make Second Wind use it.
5. Normalize healing potions into capabilities, or at least make potion use return the same effect result shape.
6. Add support for monster special attacks using the capability model.
7. Move combat event payloads to `effects` as the primary representation.
8. Rename or replace `FeatureGrant` with a more general capability/resource model once the compatibility layer is thin.

## Open Questions

- Should passive traits be represented as capabilities, modifiers, or both?
- How should targeting definitions express areas, saving throws, and multi-target effects?
- Should conditions be first-class model objects before complex debuffs land?
- How much of monster stat block text should be parsed automatically versus normalized by curated adapters?
- Should item-granted capabilities live on the actor only while equipped, or should inventory items expose them dynamically?

