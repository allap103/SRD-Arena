# Combat Action Architecture

## Status

This is the target architecture for executable combat content, not a
description of the current implementation. It supersedes the proposed
universal authored-capability schema. The full exploration is preserved on
branch `archive/unified-capability-schema` at commit `f0ae9ce`.

## Core decision

Author content in the form natural to its source, then share rules below that
boundary:

```text
spell JSON -------------> spell interpreter -----------+
monster-action JSON ----> monster-action interpreter --+--> action offer
class-feature Python ---> feature implementation -------+        |
equipment definition ---> equipment provider -----------+        v
                                                          typed invocation
                                                                 |
                                                                 v
                                                       shared domain rules
```

The project does **not** need one universal authored `Capability` object.
Existing types may keep that name while they are migrated, but new design work
should use the more precise terms *spell definition*, *monster action*, *class
feature*, *action offer*, *invocation*, and *effect*.

Limited duplication in source-specific orchestration is acceptable. Duplicate
core combat-rule semantics are not; those belong in shared domain rules.

## Ownership

| Layer | Owns |
| --- | --- |
| Source definition | Intrinsic source rules: a spell's level, components, default casting time, range, targeting, and scaling; a monster action's fixed statistics and recharge rule; a feature's unique behavior. |
| Provider or grant | Who can use the definition, contextual modifiers or overrides, action-economy access, and the concrete resource pool and cost for this actor. Spell-slot use and NPC daily uses belong here, not to the spell. |
| Action offer | The selectable choice exposed consistently to controllers, the UI, and ML clients. |
| Invocation | One exact occurrence, including actor, chosen targets, source, runtime identity, lifecycle state, and traits such as `cast_spell`. |
| Domain rules | The semantics and enforcement of attacks, saving throws, damage, healing, conditions and effects, geometry, resources, duration, and reaction/event sequencing. |

An attack spell and a monster attack may use the same attack and damage rules
without sharing an authored representation. Their invocations retain enough
context to trigger different reactions. Nested reactions such as Counterspell
must refer to one exact invocation and may suspend and resume other
invocations.

## Current migration point

`EncounterAction` is already the common action-offer envelope.
`ActionExecutionContext` is the closest current invocation shell, but there is
not yet a persistent typed invocation model, and spell attacks and monster
attacks still use separate resolution paths. The diagram above is the target.

## Declarative content and Python

Spells and monster actions should use their source-specific declarative schemas
when common interpreters can express them clearly. Class features are
Python-first because they are a smaller, highly varied set and can be
implemented class by class.

A spell may use one of three implementation depths:

1. A declarative definition interpreted entirely by shared domain rules.
2. A declarative definition with a registered Python resolver for its unusual
   resolution step.
3. A registered Python implementation for the complete spell orchestration.

Custom handlers are selected by closed, validated identifiers. Authored files
must never contain arbitrary Python import paths. A handler still creates the
normal spell invocation and uses the common controller, action-economy,
resource, reaction, event, randomness, and effect systems. Prefer handlers that
return typed domain operations over unrestricted mutation of encounter state.

> If supporting a spell declaratively requires a new construct that is highly
> specific and unlikely to be reused, implement that spell in Python. If
> several handlers later duplicate the same rule, extract it as a shared domain
> primitive.

## Lessons retained from the schema exploration

- Share stable rule semantics, not merely similar JSON shapes.
- Model source, applier, subject, effect instance, invocation, and decision
  identities explicitly where rules depend on them.
- Keep conditions, ongoing effects, and creature relationships distinct even
  when eligibility consults all three.
- Keep geometry algorithms in the domain; content only describes shapes,
  ranges, and choices.
- Generate occurrence-specific identities at runtime rather than authoring
  them in reusable content.
- Scope shared primitives precisely. For example, blocking Opportunity Attacks
  and blocking every Reaction are different effects.
- Version source schemas. Prefer mechanical content migration for semantic
  changes over permanent compatibility branches in runtime code.

## Non-goals

- A single schema that makes spells, monster actions, class features, and items
  look identical.
- A declarative construct for every unique rule in the SRD.
- Source-specific code that bypasses the common invocation lifecycle or domain
  rules.
