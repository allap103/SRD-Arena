# Combat Spell Mechanics Coverage

## Purpose

This document identifies representative SRD 5.2.1 spells that the executable
spell schema must be able to describe. The goal is schema coverage, not an
implementation schedule: a mechanic may be representable while its runtime
support is still partial, blocked, or intentionally out of scope.

The resulting concrete contract and JSON examples are documented in
[`spell_capability_schema.md`](spell_capability_schema.md).
The implementation order is documented in
[`spell_implementation_batches.md`](spell_implementation_batches.md).

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
| Confusion, Prismatic Spray | Random outcome table | Typed dice table, weighted or ranged results, nested rolls, per-target rolls, result-specific behavior or effects | Random selection must remain deterministic under an injected roller and expose the selected table result in events |
| Shield, Hellish Rebuke, Counterspell, Feather Fall | Reaction casting | Typed triggering event, inherited source or target, timing window, reaction and spell-resource cost, trigger-specific eligibility | Casting interrupts another action and then either modifies, responds to, or cancels part of its pending resolution |
| Call Lightning, Flaming Sphere, Heat Metal, Moonbeam, Sunbeam, Vampiric Touch | Repeated spell activation | Persistent spell instance, granted action or Bonus Action, retained area/object/target state, repeated resolution, optional repositioning | Later activations reference the original cast level, caster statistics, and spell instance without consuming another slot |
| Magic Missile, Scorching Ray, Chain Lightning, Chromatic Orb | Projectile allocation and propagation | Variable projectile count, same-or-different target allocation, simultaneous effects, independent attacks, secondary-target range, conditional bounce | Parameterized targeting must preserve projectile identity, target assignments, resolution order, and propagation limits |
| Flesh to Stone, Contagion, Prismatic Spray | Accumulated save outcomes | Per-spell-instance success and failure counters, nonconsecutive results, threshold branches, permanent or extended outcome | Repeat-save state records both counters and transitions atomically when either threshold is reached |
| Mirror Image, Sanctuary | Attack and targeting interception | Attack redirection, target replacement or reselection, trigger-specific bypass requirements, consumable protective instances | Effects hook into an in-progress attack or targeting pipeline before the original result becomes final |
| Death Ward | Defeat prevention | Replace the first drop to 0 HP with 1 HP, negate instant death without damage, consume the protective effect after either branch | Damage and instant-death pipelines expose a pre-defeat interception stage before marking a creature defeated or killed |
| Dispel Magic, Counterspell, Antimagic Field, Globe of Invulnerability | Spell interaction and suppression | Spell identity and level, casting interruption, ability checks against spell level, effect ending, spatial suppression, immunity exceptions | Suppression disables an existing effect without deleting it; countering can waste casting action while preserving its slot according to the rule |
| Polymorph, Shapechange, Alter Self | Transformation and form replacement | Form selection, eligibility by CR or level, statistic replacement, retained properties, temporary HP, anatomy restrictions, equipment merging | One combatant identity persists while its effective statistics, available actions, and spatial properties change |
| Banishment, Maze, Blink | Temporary battlefield removal | Plane or off-board state, removal and return triggers, return-space selection, nearest-free-space fallback, perception and interaction restrictions | Removed creatures remain encounter participants but are excluded from ordinary targeting, occupancy, and turn interactions as specified |
| Warding Bond | Linked-creature effect | Source-target relationship, range-dependent benefits, damage mirroring, source-defeat termination, uniqueness constraints | Damage propagation must retain causal attribution and prevent recursive triggering loops |
| Haste, Time Stop | Turn and action scheduling | Constrained extra action, multiple consecutive turns, early termination based on actions or movement, end-of-effect penalty | The turn scheduler and action-resource model must support temporary grants without treating controllers differently |
| Reverse Gravity, Fly, Levitate | Vertical movement and gravity | Three-dimensional areas, elevation, ceilings, hovering, upward and downward falling, anchored-state checks | Depends on the cubic z-axis model, occupied volumes, falling, landing, and vertical collision queries |
| Command, Compulsion, Dominate Person | Compelled behavior and delegated control | Selected command or behavior, forced action and movement policy, target-controller substitution, repeat saves and termination triggers | A rule effect constrains or temporarily supplies decisions without changing the underlying combatant identity |
| Hex, Hunter's Mark, Divine Favor | Attack and damage riders | Marked target relationship, qualifying attack or hit trigger, additional damage, target transfer, ability-choice modifier | Attack resolution discovers matching rider providers and attributes their damage to the originating spell instance |
| Animate Objects | Object transformation into combatants | Object selection and size cost, stat-block conversion, shared initiative timing, commands, fallback behavior, damage carry-over on reversion | Requires modeled objects plus temporary combatants whose defeat restores the original object state |
| Delayed Blast Fireball | Delayed accumulating effect | Persistent interactable bead, damage growth on source turn end, touch interaction, save-gated throwing, collision and early detonation | Spell-instance state accumulates dice and can be moved or detonated by creatures other than the caster |
| Contingency, Glyph of Warding, Symbol | Dormant triggered spell | Stored spell or effect, authored trigger, trigger exclusions, object or surface attachment, delayed activation, inherited target or area | Requires a constrained trigger vocabulary; arbitrary natural-language triggers may remain partial or out of scope |
| Regenerate, Heroism | Recurring beneficial effect | Immediate healing, start-of-turn healing or temporary HP, caster-derived value, duration, bodily restoration omission where unsupported | Turn triggers apply beneficial effects repeatedly and stop cleanly when the parent spell instance ends |
| Aid | Current and maximum HP modification | Multiple chosen targets, current HP increase, maximum HP increase, fixed duration, slot scaling | Ending the effect recalculates maximum HP without treating the granted current HP as ordinary healing |
| Telekinesis | Repeated target manipulation | Granted Magic action, creature/object choice, target replacement, save-gated three-dimensional movement, temporary Restrained, sustained suspension | Switching targets releases prior state; repeated activation can maintain an airborne target across turns |
| Fire Shield | Retaliatory effect | Cast-time mode choice, damage resistance, light, melee-hit trigger, range requirement, automatic damage to triggering attacker | Incoming-hit resolution emits a retaliation after confirming attack mode and attacker distance |
| Arcane Hand, Spiritual Weapon | Controllable spell entity | Independent position, size or non-occupancy, AC and HP where applicable, granted movement/action, selectable modes, cover and terrain effects | A spell-created entity can be targeted, moved, damaged, and used as the origin of later actions without becoming a normal summoned creature |

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

## Scope decisions

- Mounted combat is not currently supported. Find Steed and Phantom Steed are
  therefore outside the active spell catalog.
- Find Greater Steed is not part of the current SRD 5.2 spell catalog. If it is
  added from another supported source later, only the summoned creature's
  ordinary combat functionality is in scope; mounted-combat functionality is
  not.
- Creation, Control Weather, Imprisonment, Planar Ally, Prayer of Healing,
  Sequester, Tiny Hut, Unseen Servant, and Wind Walk are outside the active
  catalog. Their long casting process produces ordinary scenario configuration,
  no lasting combat state, open-ended behavior, or no meaningful tactical
  participation under the current simulator scope.
