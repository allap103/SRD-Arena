# Condition Runtime Semantics

This document records how SRD Arena represents and evaluates conditions. It is
an implementation reference, not a source for rules content or presentation
text.

## Applied and Effective Conditions

An applied condition is a concrete runtime instance with its own source,
origin, target, and duration. Multiple effects can apply the same condition,
and every application keeps its own duration. The condition's mechanics are
evaluated once regardless of the number of active applications.

An effective condition is the result of evaluating all applied conditions,
their implications, immunities, and temporary suppression.

For example, Paralyzed implies Incapacitated. An action requiring an
Incapacitated target therefore accepts a Paralyzed target without needing to
know every condition that implies Incapacitated.

## Applier, Means, and Origin

Condition provenance distinguishes three concepts:

- The **applier** is the creature responsible for applying the condition.
- The **means** is the action, spell, feature, item, or environmental rule used.
- The **origin** is the particular runtime use or casting that produced it.

This supports requirements with different provenance constraints. A Mind
Flayer's Extract Brain requires Incapacitated from any source but Grappled by
that Mind Flayer.

## Condition Consequences

Consequences must be modeled according to their lifecycle.

- An inseparable consequence can be derived during rule evaluation.
- A consequence that can persist independently must be applied as its own
  runtime condition.
- Lower-level mechanical traits remain derived when they cannot be removed or
  suppressed independently.

Paralyzed implying Incapacitated is a derived relationship. Removing one
Paralyzed application removes only the Incapacitated contribution from that
provider.

Unconscious requires mixed behavior:

- Incapacitated is derived and ends with Unconscious.
- Prone is applied as an independent consequence, subject to Prone immunity.
- Ending Unconscious does not stand the creature up, so Prone remains until
  removed through its own rules.

Condition definitions therefore need per-consequence lifecycle policies rather
than one universal implication mechanism.

## Immunity and Suppression

Immunity and suppression are different mechanics.

### Immunity

Immunity prevents a new condition from taking hold. The rejected condition is
not stored as a dormant runtime application and cannot activate later when the
immunity ends.

For example, Charmed applied while Mind Blank grants Charmed immunity is
rejected. Ending Mind Blank does not cause that rejected Charmed condition to
appear.

An implied condition is also checked against the target's immunity. A Black
Pudding can be Unconscious and Incapacitated while avoiding the separately
applied Prone consequence because it is immune to Prone.

### Suppression

Suppression temporarily disables an already-existing condition without removing
its runtime application. When suppression ends, the condition becomes effective
again if it has not otherwise expired or been removed.

The 2024 Calm Emotions spell demonstrates the distinction: it grants immunity
to new Charmed and Frightened conditions and separately suppresses instances
that already existed.

Suppression should therefore be represented explicitly as an ongoing runtime
effect referring to the affected condition applications or matching condition
set. It must not be inferred merely from gaining immunity.

## Static and Conditional Immunities

Unconditional stat-block immunities are typed creature-definition data.
Temporary immunity granted by a spell or effect is ongoing encounter state.

Some source records contain conditional notes:

- An Archmage's Charmed immunity is present while Mind Blank is active. The
  spell, rather than the Archmage stat block, provides the runtime immunity.
- Rules as written, a Vampire Familiar's Charmed immunity excludes effects from
  its vampire master. SRD Arena intentionally treats this as unconditional
  immunity because encounters between a familiar and its own master are outside
  the supported scope. This deviation is recorded in `rules_deviations.md`.

Conditional source notes are preserved by content loading but are not treated
as unconditional static immunity.

## Application and Removal

Applying a condition:

1. Identifies the applier, means, and runtime origin.
2. Checks static, temporary, and source-sensitive immunity.
3. Rejects the application with a structured result when immune.
4. Otherwise stores an independent condition instance.
5. Applies any independently persistent consequences.

Each runtime origin receives a stable unique ID. Reasserting the same condition
from the same ongoing origin can refresh that instance. A later use of the same
action creates a different origin and therefore a separate duration.

Removal operations have distinct scopes:

- Expiration or a successful save removes one application or effect subtree.
- A cure that ends a named condition removes all matching applications unless
  its text limits the source or count.
- Ending an effect root removes its dependent runtime state.
- Removing a derived provider removes only that provider's contribution.

Exhaustion is the stacking exception and uses explicit gain, remove, and set
level operations.

## Condition Spell Lifecycles

A concentration spell is represented by an `OngoingEffect` root. Conditions
created by that casting reference the ongoing effect as their parent and root,
while sharing the casting's runtime origin. Ending concentration removes the
root and all condition applications produced by that casting.

Concentration currently ends when:

- the caster starts concentrating on another effect;
- the caster fails the Constitution saving throw caused by taking damage;
- the caster becomes Incapacitated or is defeated;
- the spell reaches its maximum duration.

Repeat saving throws are parameters of the ongoing effect rather than of the
condition. A successful repeat save removes the complete effect subtree. This
keeps Paralyzed reusable while allowing Hold Person and future spells to define
different repeat-save schedules.

Lesser Restoration presents its removable conditions as explicit action
choices. Resolution therefore never depends on collection order when a target
has more than one removable condition.
