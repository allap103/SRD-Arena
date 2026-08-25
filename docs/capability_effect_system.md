# Historical: Capability and Effect System Design

> Superseded design exploration. Do not follow its universal authored
> `Capability`, source-normalization, or migration proposals. The useful
> lessons about rule hooks, effect results, resource semantics, and custom
> resolvers are retained in
> [Combat Action Architecture](combat_action_architecture.md).

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
- Represent passive rule changes without hardcoding feature names into combat.
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

Content sources normalize into grants. There are two primary kinds:

- **Capability grants** provide active, triggered, or special actions that resolve into effects.
- **Rule grants** modify an existing resolution pipeline at a defined hook.

A single source can grant both. For example, a magic item can grant an activated capability
and a passive rule that modifies saving throws while the item is equipped.

### Capability

A capability is an action-like ability granted by a creature or item. It may be active,
triggered, or usable as a special attack.

```python
@dataclass
class Capability:
    id: str
    name: str
    source_type: str  # class, feat, background, species, item, monster
    source_id: str
    action_type: str  # action, bonus_action, reaction, triggered, special_attack
    resolver: str
    data: dict[str, object]
    cost: dict[str, int] = field(default_factory=dict)
    uses: ResourceDefinition | None = None
    targeting: TargetingDefinition | None = None
```

At runtime, encounter logic should mostly care about `action_type`, `cost`, `uses`, `targeting`, and `resolver`. The source tells us where the capability came from, but not necessarily how it resolves.

### Rule Grant

A rule grant changes how another capability or core mechanic resolves. It does not produce
an effect by itself and should not require feature-specific branches in attack, damage, or
saving-throw code.

```python
@dataclass
class RuleGrant:
    id: str
    source_type: str
    source_id: str
    trigger: str
    operation: str
    conditions: dict[str, object] = field(default_factory=dict)
    parameters: dict[str, object] = field(default_factory=dict)
```

Great Weapon Fighting can normalize into:

```python
RuleGrant(
    id="great_weapon_fighting",
    source_type="fighting_style",
    source_id="great_weapon_fighting|phb",
    trigger="weapon_damage_rolled",
    operation="reroll_matching_dice",
    conditions={
        "attack_type": "melee",
        "wielded_with": "two_hands",
        "weapon_properties_any": ["two-handed", "versatile"],
    },
    parameters={
        "values": [1, 2],
        "maximum_per_die": 1,
        "must_use_replacement": True,
        "optional": True,
    },
)
```

The damage pipeline queries applicable rules by trigger and context. A character without
this rule uses the original damage roll. A character with it receives reroll choices for
qualifying dice. The runtime understands `reroll_matching_dice`; it does not contain a
branch for Great Weapon Fighting.

Initial resolution hooks should include:

- `attack_roll_created`
- `attack_roll_resolved`
- `weapon_damage_rolled`
- `damage_resolved`
- `ability_check_created`
- `ability_check_resolved`
- `saving_throw_created`
- `saving_throw_resolved`

The operation vocabulary should remain small and reusable. Likely early operations include:

- `reroll_matching_dice`
- `reroll_selected_dice`
- `reroll_entire_pool`
- `add_dice`
- `modify_roll`
- `grant_advantage`
- `grant_disadvantage`
- `modify_damage`

Rules may create a decision rather than immediately changing a roll. The engine determines
eligible dice, selection limits, replacement rules, and costs. Human and RL clients receive
the same legal actions and submit selections through the encounter decision system.

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

### Status

A status is persistent or temporary state that can contribute rule grants. Buffs, debuffs,
and named conditions should use the same status model rather than separate execution paths.

```python
@dataclass
class Status:
    id: str
    source_ref: str
    target_ref: str
    duration: DurationDefinition
    rules: list[RuleGrant] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
```

Applying or removing a status is an effect. The status itself is not an effect:

```python
EffectResult(
    kind="apply_status",
    target_ref="enemy:0",
    data={"status": frightened_status},
)
```

This distinction gives the runtime a consistent flow:

```text
source -> capability or rule grant
capability -> ordered effects
rule -> modifies capability resolution
effect -> changes game state or applies a status
status -> contributes temporary rules
```

## Source Normalization

Different content sources should normalize into capability and rule grants before combat
runtime sees them.

Suggested source modules:

```text
game/capabilities/
  types.py
  registry.py
  rules/
    registry.py
    operations.py
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

Source modules answer: "What capabilities and rules does this content grant?"

Resolvers answer: "What happens when this capability is used?"

Rule operations answer: "How does this grant modify the current resolution?"

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
        "modifier": "creature.level",
    },
)
```

The same `healing.self` resolver could also support potions, species traits, and magic items.

Source data can provide identity, source, ownership requirements, option lists, and structured
values such as dice expressions. Much of the mechanical behavior is currently prose. That
prose should not be interpreted as executable rules at runtime. Curated normalization data
can map canonical source IDs to generic rules:

```text
game data -> source loader -> normalization catalog -> runtime grants
```

The normalization catalog should preferably be structured data. Custom Python adapters remain
appropriate when source data requires edition-aware interpretation or complex normalization.

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

Generic rule operations should follow the same principle. Features with equivalent mechanics
should normalize into the same operation with different conditions and parameters. For
example, Great Weapon Fighting, Empowered Spell, and a species trait may all use selective
die replacement without sharing feature-specific runtime code.

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

1. Keep the current `ClassFeature` loading path working.
2. Introduce `Capability`, `EffectResult`, and `CapabilityActionResult` alongside existing feature types.
3. Convert Second Wind internally to return `CapabilityActionResult` effects while preserving the existing event payload for compatibility.
4. Add a generic `healing.self` resolver and make Second Wind use it.
5. Normalize healing potions into capabilities, or at least make potion use return the same effect result shape.
6. Add support for monster special attacks using the capability model.
7. Move combat event payloads to `effects` as the primary representation.
8. Introduce `RuleGrant`, a rule registry, and explicit resolution hooks.
9. Normalize Great Weapon Fighting into `reroll_matching_dice` as the first passive rule.
10. Route rule-created choices through the encounter decision system.
11. Add first-class statuses whose modifiers are represented by temporary rule grants.
12. Keep `ClassFeature` narrow; introduce separate capability and resource models rather than generalizing it.

## Open Questions

- How should targeting definitions express areas, saving throws, and multi-target effects?
- How much of monster stat block text should be parsed automatically versus normalized by curated adapters?
- Should item-granted capabilities live on the creature only while equipped, or should inventory items expose them dynamically?
- How should conflicting rules be ordered when several grants modify the same resolution hook?
- Which status durations must be persisted in encounter snapshots?

