# Spell Implementation Waves

## Purpose

This plan orders executable spell work by shared engine capability rather than
spell level. A spell enters the first wave that can express and execute all of
its combat-relevant behavior. This prevents spell-name handlers and avoids
building several unrelated subsystems at once.

Spell JSON remains the source of truth. Each wave includes schema enrichment,
translation, execution, presentation, and tests for its spells. A spell is not
considered implemented merely because its source fields can be loaded.

The exhaustive, machine-validated assignment is maintained in
[`spell_implementation_manifest.json`](spell_implementation_manifest.json).
Every active spell appears there exactly once. Wave 1 assignments are
committed; later assignments are provisional and should be reviewed when their
preceding wave finishes.

## General rules

- `complete` means every combat-relevant branch in the supported scope runs.
- `partial` is allowed only with explicit omissions. It is appropriate for a
  genuinely out-of-scope side effect, such as Fireball igniting unattended
  objects before environmental fire exists. It must not conceal a mechanic
  merely deferred to a later wave.
- `blocked` is used when mechanics are enriched but their required executor is
  scheduled for a later wave.
- A spell requiring mechanics from several waves belongs to the latest of
  those waves.
- Shared mechanics are implemented once and reused by stat-block actions,
  spells, conditions, and later character features where applicable.
- Spells with casting times longer than one action are not selectable during
  an encounter. They remain supported only when their completed effect creates
  meaningful ongoing combat state for scenario setup.

## Wave 1: rolls, conditions, and concentration

### Scope

Wave 1 contains only spells composed from:

- spell attack rolls;
- saving throws;
- automatic application where needed for a condition;
- immediate damage on a resolved attack or save;
- half or no damage on a successful save;
- applied conditions;
- fixed, turn-relative, and spell-owned condition durations;
- concentration ownership and cleanup;
- repeat saves and condition progression;
- ordinary creature targets and existing cone, cube, line, and sphere areas;
- simple dice and target-count scaling.

Wave 1 deliberately excludes healing, temporary HP, general bonuses and
penalties, forced movement, persistent areas, reactions, damage riders,
granted actions, summons, transformations, spell entities, encounter
departure, and unrestricted authored behavior.

### Batch 1A: immediate attacks and saves

Start with spells whose result ends after the attack or save:

- Acid Splash
- Burning Hands
- Fire Bolt
- Inflict Wounds
- Poison Spray
- Sacred Flame
- Shatter
- Fireball
- Lightning Bolt
- Blight
- Cone of Cold
- Flame Strike
- Circle of Death

Fire Bolt, Shatter, and Fireball may initially be `partial` only for their
explicit object or environmental side effects. Their creature damage must be
complete.

### Batch 1B: condition lifecycle

Add spell-owned conditions, concentration, repeat saves, and early-ending
events:

- Animal Friendship
- Charm Person
- Color Spray
- Greater Invisibility
- Hideous Laughter
- Invisibility
- Sleep
- Blindness/Deafness
- Hold Person
- Charm Monster
- Hold Monster

This batch must prove that ending concentration or the spell instance removes
only effects owned by that instance. Early-ending rules such as damage waking a
target must use shared effect events rather than spell-name checks.

### Batch 1C: compositions of the same primitives

Finish the wave with spells that remain within the same vocabulary but compose
it more deeply:

- Ray of Sickness: attack, damage, save, and condition.
- Ice Knife: attack followed by an area save.
- Scorching Ray: repeated spell attacks with target allocation.
- Eldritch Blast: repeated attacks with level scaling.
- Weird: condition application and repeat-save damage for multiple targets.

These are Wave 1 capstones, not permission to introduce generic event riders or
persistent hazards early.

### Exit criteria

Wave 1 is complete when:

1. Every listed spell has explicit mechanics and an honest implementation
   status.
2. Action discovery derives legal targets from those mechanics.
3. Attack and save rolls use the shared injected roller and produce structured
   events.
4. Area saves resolve independently for every affected creature.
5. Condition provenance records the spell instance, source, and target.
6. Concentration is exclusive per caster, reacts to damage, and removes all
   owned effects when it ends.
7. Repeat saves and staged condition transitions survive turn boundaries.
8. Slot and cantrip scaling are evaluated from a snapshotted cast level.
9. The UI and model-facing action API expose the same choices without
   enumerating target names in action labels.

## Wave 2: immediate support and creature modifiers

Add effects that alter a creature without requiring a new event or spatial
entity:

- healing and temporary HP;
- condition and effect removal;
- AC, speed, saving-throw, attack, and damage modifiers;
- resistance, immunity, maximum-HP changes, and ordinary movement modes;
- automatic damage and projectile allocation;
- grouped modifiers such as Slow.

Representative spells include Cure Wounds, Healing Word, Aid, False Life,
Bless, Bane, Mage Armor, Shield of Faith, Barkskin, Lesser Restoration,
Greater Restoration, Protection from Energy, Stoneskin, Magic Missile, and
Slow. Flesh to Stone also belongs here because its successful initial save
applies a Speed modifier in addition to its condition progression.
Hypnotic Pattern and Power Word Stun also wait for this wave because each has a
Speed-0 branch in addition to its conditions. Phantasmal Killer applies
Disadvantage rather than the Frightened condition in SRD 5.2.

## Wave 3: event-driven spells and interruption

Extend the action lifecycle with typed reaction windows and ongoing event
providers:

- reaction casting;
- post-hit casting and damage riders;
- incoming-attack modification and target interception;
- retaliation and linked damage;
- defeat prevention and on-kill effects;
- effect transfer and later target selection.

Representative spells include Shield, Counterspell, Hellish Rebuke, Feather
Fall, Divine Smite, Ensnaring Strike, Searing Smite, Hex, Hunter's Mark,
Sanctuary, Mirror Image, Fire Shield, Warding Bond, Death Ward, and Finger of
Death. Contagion belongs here because it intercepts later attempts to remove
its Poisoned condition rather than merely applying a condition and repeat save.

## Wave 4: persistent spatial effects

Introduce spell-owned battlefield entities and their spatial event ledger:

- persistent areas, walls, emanations, and hazards;
- entry, area-movement, and turn triggers;
- difficult terrain, obscurement, cover, and visibility;
- autonomous and caster-directed area movement;
- forced movement and escape checks;
- composite and oriented areas.

Representative spells include Fog Cloud, Darkness, Grease, Entangle, Web,
Spike Growth, Moonbeam, Spirit Guardians, Stinking Cloud, Black Tentacles,
Wall of Fire, Cloudkill, Blade Barrier, Wall of Ice, Wall of Thorns, and Fire
Storm.

## Wave 5: granted actions and spell entities

Add spell instances that expose later actions or create independently tracked
entities without creating ordinary creatures:

- granted Actions, Bonus Actions, and Magic actions;
- cast-level snapshots used by later activations;
- target history and switching;
- movable, damageable, or held spell entities;
- repeated activation without consuming another spell slot.

Representative spells include Flame Blade, Spiritual Weapon, Flaming Sphere,
Heat Metal, Call Lightning, Vampiric Touch, Sunbeam, Eyebite, Telekinesis,
Arcane Hand, and Delayed Blast Fireball.

## Wave 6: summons, control, and transformations

Add temporary combatants and changes to creature identity or decision policy:

- summoned and created combatants;
- shared or independent initiative;
- commands, fallback behavior, and controller substitution;
- form replacement and retained statistics;
- object-to-creature transformation;
- compelled behavior.

Representative spells include Find Familiar, Animate Dead, Create Undead,
Giant Insect, Summon Dragon, the Conjure family, Animate Objects, Dominate
Person, Polymorph, True Polymorph, Shapechange, and Simulacrum.

Mounted-combat rules remain out of scope. A future Find Greater Steed source
may expose only the summoned creature's ordinary combat functionality.

## Wave 7: encounter-scale movement and scheduling

Build mechanics that change participation, dimensions, or the turn scheduler:

- temporary and permanent battlefield departure;
- return placement and nearest-free-space fallback;
- encounter escape and terminal draw policy;
- consecutive or additional turns;
- constrained extra actions;
- three-dimensional movement, falling, and occupied volumes.

Representative spells include Banishment, Blink, Maze, Etherealness, Plane
Shift, Teleport, Word of Recall, Haste, Time Stop, Fly, Levitate, Reverse
Gravity, and Gate.

Teleport removes transported combatants from the encounter. If every surviving
combatant on that team leaves, the encounter ends as a draw; this follows a
general encounter-departure rule rather than a Teleport-specific terminal
handler.

## Wave 8: prepared, random, and exceptional orchestration

Complete the remaining combat catalog with mechanics that require mature
effect, event, and scenario systems:

- random and nested outcome tables;
- dormant authored triggers;
- spell suppression, dispelling, and level comparisons;
- prepared battlefield wards;
- unusual causal or accumulating state;
- carefully bounded exceptional spell behavior.

Representative spells include Confusion, Prismatic Spray, Contingency, Glyph
of Warding, Symbol, Antimagic Field, Dispel Magic, Globe of Invulnerability,
Forbiddance, Guards and Wards, Hallow, Antipathy/Sympathy, Magic Jar, Mirage
Arcane, Sunburst, and Wish. Sunburst waits for this wave because dispelling
magical Darkness is a combat-relevant part of the spell, not a silent omission.

Wish should first support duplication of an executable eligible spell. Its
open-ended reality-altering use remains explicitly out of scope.

## Review after each wave

At the end of every wave:

1. Reclassify active spells whose remaining behavior is no longer appropriate
   for the combat simulator.
2. Audit enriched records for silent omissions and spell-name dispatch.
3. Add a scenario showcasing the new shared capabilities rather than one
   scenario per spell.
4. Profile action discovery and resolution before expanding the next mechanic
   family.
5. Confirm that serialization contains all spell-instance state required by
   deterministic model interaction and replay.
