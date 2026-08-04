# Combat Spell Mechanics Coverage

## Purpose

This document identifies representative SRD 5.2.1 spells that the executable
spell schema must be able to describe. The goal is schema coverage, not an
implementation schedule: a mechanic may be representable while its runtime
support is still partial, blocked, or intentionally out of scope.

SRD Arena's spell JSON files are the canonical source of truth. Prose remains
human-readable rules text and must not be parsed at runtime. Explicit mechanics
enrichment supplies relationships, choices, triggers, formulas, and exceptions
that the existing structured fields do not express unambiguously.

Spells retain a distinct top-level schema from stat-block actions. Both schemas
should reuse lower-level definitions for targets, areas, requirements, effects,
durations, rolls, and outcome stages.

## Coverage matrix

| Representative spells | Mechanics family | Schema capabilities required | Important runtime implications |
| --- | --- | --- | --- |
| Shatter, Fireball, Cone of Cold, Burning Hands | Direct area damage | Fixed area geometry, save ability, damage formula and type, half or no damage on success, slot scaling | Select or aim area, resolve each target independently, apply damage through the shared pipeline |
| Hold Person, Blindness/Deafness | Condition application | Creature target requirements, saving throw, condition effect, duration, repeat saves, concentration where applicable | Explainable target eligibility, condition provenance, independent target effect instances |
| Slow | Compound ongoing modifier | Chosen targets within an area, grouped ongoing effect, speed multiplier, AC modifier, Dexterity-save modifier, reaction prohibition, Action/Bonus Action restriction, attack limit, conditional Somatic-spell failure, repeat save | All child modifiers share one spell-instance root and end together |
| Sleep | Staged resolution | Chosen creatures within an area, first failed save effect, repeat save, second-failure transition, automatic save success requirements, wake-up triggers | Effect progression from Incapacitated to Unconscious; sleep trait and Exhaustion-immunity queries |
| Summoning spells | Created combatants | Template selection, count, legal placement, cast-level scaling, duration, concentration, commands, ownership and controller policy | Spawn encounter combatants, schedule turns, remove summons when their parent effect ends |
| Flame Blade | Held manifestation and granted actions | Free-hand requirement, held manifestation, granted Magic action, granted Bonus Action, melee spell attack, cast-level snapshot, light emission | Actions exist only while the parent spell instance is active; releasing and re-evoking alter manifestation state |
| Eyebite | Reusable granted spell action | Initial effect, granted Magic action, selectable effect branches, per-casting target history, outcome-dependent target exclusion | Granted actions refer to persistent spell-instance state rather than starting a new casting |
| Fire Storm | Constructed composite area | Up to ten 10-foot cubes, caster-authored placement, contiguity policy, union semantics, save and damage | Multi-step area placement; action API accepts structured parameters rather than enumerating every layout |
| Ensnaring Strike, Divine Smite | Post-hit conditional casting | Attack-hit trigger, weapon or attack-mode requirements, inherited target, constrained Bonus Action timing, spell-resource consumption | A triggered Bonus Action decision pauses and later resumes the parent attack lifecycle |
| Wall of Fire | Persistent oriented hazard | Straight-wall or ring choice, custom dimensions, opacity, selected hazardous side, initial resolution, entry and turn-end triggers, concentration | Persistent spatial entity with orientation, hazardous subregion, event hooks, and rendering |
| Cloudkill | Moving persistent hazard | Persistent sphere, Heavy Obscurement, initial/entry/turn-end resolution, autonomous movement, once-per-target-per-turn limit, strong-wind termination | Area movement can enter creature spaces; resolution requires a per-turn trigger ledger |
| Finger of Death | Attributed on-kill effect | Save damage, causal kill attribution, branch-specific Humanoid requirement, delayed source-turn trigger, creature replacement | Preserve damage source, corpse position, delayed event, Zombie creation, team and controller assignment |
| Lesser Restoration, Greater Restoration | Selected effect removal | Touch targeting, selection from currently removable effects, condition removal, Exhaustion-level reduction, curse removal, ability-score restoration, HP-maximum restoration | Action discovery depends on target state; only the selected effect is removed |
| Fog Cloud | Persistent obscurement | Persistent point-origin sphere, Heavy Obscurement property, concentration, strong-wind termination, radius slot scaling | Visibility and targeting queries consult spatial effect entities; environmental effects can terminate them |

## Shared schema vocabulary

The matrix implies reusable typed definitions in the following groups.

### Targeting and placement

- self, creature, object, point, space, and area targets;
- allies, enemies, willing creatures, chosen creatures, or all occupants;
- creature-type, size, condition, trait, visibility, and source-relative
  requirements;
- single, multiple, and "up to" target counts;
- fixed, composite, wall, aura, and persistent area geometry;
- parameterized and multi-step placement;
- target inheritance from triggering events.

### Resolution

- spell attacks, saving throws, automatic effects, ability checks, and
  contested checks;
- independent resolution for multiple targets;
- success, failure, and staged outcome branches;
- repeat saves and outcome-dependent transitions;
- fixed and caster-derived values such as spell save DC and spell attack
  modifier;
- resolution limits scoped by target, turn, round, or spell instance.

### Effects

- damage, healing, temporary HP, conditions, and effect removal;
- roll, AC, speed, action-economy, attack-count, resistance, immunity, and
  visibility modifiers;
- forced movement, teleportation, movement modes, and terrain changes;
- granted actions and held manifestations;
- persistent spatial entities and created combatants;
- condition and effect progression;
- delayed and outcome-triggered effects.

### Lifecycle and events

- instantaneous, timed, concentration, source-relative, and event-based
  durations;
- grouped effects owned by one spell-instance root;
- casting, attack-hit, damage, defeat, kill, movement, area movement, turn,
  and effect-ending events;
- cleanup when concentration, duration, source state, environmental effects,
  or explicit removal ends the parent effect;
- per-casting memory such as previous target outcomes.

### Choices and scaling

- selectable targets, areas, damage types, conditions, forms, and effect
  branches;
- additional dice, targets, projectiles, area size, duration, or other typed
  changes by slot level;
- cast-level snapshots retained by ongoing and granted effects.

## Spell definition and spell access

The canonical spell definition describes what a spell does. A creature's spell
access describes how that creature can cast it.

Spell access must support:

- shared spell-slot pools with selectable cast levels;
- per-spell limited uses and reset periods;
- at-will casting;
- an authored cast level;
- caster-derived save DC and spell attack modifier.

These are resource policies rather than Player Character or NPC branches. The
same creature-neutral casting pipeline consumes whichever resource policy the
spell access declares.

## Implementation coverage

Every spell and independently selectable mechanic branch should declare one of
these statuses:

- `complete`: all combat-relevant behavior in the declared scope executes;
- `partial`: executable with explicitly listed omissions;
- `unimplemented`: intended, but no executable mechanics exist yet;
- `blocked`: encoded but dependent on missing engine capabilities;
- `out_of_scope`: intentionally excluded from the combat simulator.

Partial behavior must never be silent. For example, Fireball may implement
creature damage while explicitly omitting ignition of unattended flammable
objects until environmental objects and fire are modeled.

## Schema acceptance criteria

The spell-mechanics schema is sufficiently expressive when every
combat-relevant SRD spell can be represented without:

- parsing prose at runtime;
- dispatching on a spell name or ID;
- hiding unsupported effects or selectable branches;
- embedding controller or Player Character/NPC distinctions in spell
  resolution;
- introducing an unrestricted expression language.

Genuinely unusual orchestration may use a named, typed mechanic variant. Rules
that answer an existing engine question should instead use reusable primitives,
and unique combinations such as Slow should group those primitives under one
spell-instance root.
