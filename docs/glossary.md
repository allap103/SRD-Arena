# Project glossary

When a code concept corresponds directly to a concept defined by the game rules, use
the rules term in code. Use broader software terminology only when an abstraction
intentionally covers multiple rules concepts.

## Creature

A rules-defined creature participating in the simulation.

Use `Creature`, not `Actor`, for this domain concept.

Existing authored-content and save-data keys such as `actors`, `actor_id`, and
`actor_ref` remain supported as storage-format compatibility names. They do not
determine the terminology used by the domain model or Python API.

## Battlefield entity

Anything represented on the tactical map, potentially including creatures, objects,
and hazards. Use this broader term only when code intentionally supports more than
creatures.

## Object

A non-creature battlefield entity that may have a position, Armor Class, Hit Points,
and damage traits.

## Hazard

An environmental effect or entity that may trigger actions or participate in
initiative without being a creature.
