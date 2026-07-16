# Area Of Effect Geometry

## Purpose

This document defines the intended direction for area-of-effect geometry in the project.
It exists to separate:

- SRD-based rules we want to preserve
- project decisions we must make to implement those rules on a square grid
- temporary simplifications in the current code

The goal is to keep the long-term system SRD-compatible and clearly mark any implementation
policy that is our own addition rather than a direct SRD rule.

## Source Policy

### SRD rule

The geometry system should be based on SRD-compatible area-of-effect concepts.

### Project decision

When the SRD leaves room for implementation detail on a square grid, we explicitly document
the choice here rather than treating it as if it were part of the SRD.

### Future cleanup

If current code or content still reflects non-SRD wording or data sources, we should treat
that as temporary and remove or replace it later. This document should avoid depending on
non-SRD wording where possible.

## Core Model

The long-term AoE pipeline should be:

1. Choose a point of origin.
2. Choose an aim direction or aim point.
3. Construct a continuous geometric shape.
4. Rasterize that shape to affected grid cells.
5. Apply later filters such as total-cover blocking.
6. Map surviving cells to creatures.
7. Apply spell- or effect-specific inclusion and exclusion rules.

### Project decision

The main internal representation should be:

- continuous shape information for the geometry layer
- `origin + affected cells` for the rasterized encounter layer

This keeps geometry, cover filtering, and target selection separated.

## Scope Constraint

### Project decision

The encounter geometry system is strictly two-dimensional.

That means:

- the battlefield is treated as flat
- AoE origin, direction, and affected cells are resolved only in `x` and `y`
- elevation and vertical placement are out of scope for this system

### Project note

Tabletop D&D can involve vertical positioning and three-dimensional placement. We are
intentionally not modeling that here. If we ever add a `z` axis later, it should be treated
as a separate expansion of the geometry model rather than something implicitly supported now.

## SRD-Compatible Foundations

### SRD rule

An area of effect has a point of origin.

### SRD rule

The shape definition determines how that origin is positioned.

### SRD rule

If all straight lines from the point of origin to a location in the area are blocked by total
cover, that location is not included.

### Project note

The total-cover rule is a later filtering layer. It should not be baked into initial shape
generation.

## Geometry Layers

### Continuous geometry layer

This is the rule-facing layer.

Examples:

- cone from an origin in an arbitrary direction
- line from an origin toward an arbitrary point
- sphere or radius around a chosen point
- cube or emanation with rule-specific placement

This layer should not be limited to 8 grid directions.

### Rasterization layer

This converts the continuous shape into grid cells for encounter use.

This is where we must make explicit project decisions for squares partially covered by a
shape.

## Rasterization Policy

The SRD does not, by itself, fully specify how a continuous shape should be converted into
discrete grid cells in our implementation.

We therefore need a documented project policy.

### Candidate policy A: touched-cell

If the continuous shape touches any part of a square, that square is included.

### Candidate policy B: half-cell

Only squares with at least 50 percent coverage are included.

When a square crosses that threshold, the whole square is treated as affected in the
encounter layer.

### Project decision

For the current directional-shape system, we use configurable coverage-threshold
rasterization.

That means:

- cone, line, and cube areas are first constructed as continuous shapes
- each grid square is measured by overlap area with that shape
- a square is included only if it meets the configured minimum coverage threshold
- once included, the square is treated as fully affected

### Project note

This is a project implementation rule, not a direct SRD claim about square-grid
rasterization.

### Current project override

The threshold is now configurable in game data via `settings.json` under:

`rules.directional_aoe_cell_coverage_threshold`

The current sample game sets this to `0.1`, meaning a directional AoE square is included
once at least 10 percent of that square is covered.

### Project note

This 10 percent value is an intentional project tuning choice for now. It is not presented
as an SRD rule.

### Current limitation

The current `radius` helper still uses the older touched-cell behavior and should be migrated
to the same half-cell policy when we revisit non-directional continuous shapes.

## Shape-Specific Notes

## Directional Split

### Project decision

For implementation purposes, AoE shapes should be divided into two broad groups:

- non-directional shapes
- directional shapes

### Non-directional shapes

These do not require a chosen direction once the point of origin is known.

Current examples:

- sphere / radius
- cylinder
- emanation

### Directional shapes

These require a chosen direction in addition to the point of origin.

Current examples:

- cone
- line
- cube

### Project note

This is an implementation split, not a claim that all of these shapes behave identically.
It is meant to define whether the targeting flow must ask for direction or not.

### Cone

### SRD-compatible intent

A cone begins at a point of origin and extends outward in a chosen direction as a continuous
shape.

### Project decision

The final cone system should be aimed by direction vector or aim point, not only by one of
8 named grid facings.

### Current state

The implementation now accepts an arbitrary 2D aim vector and rasterizes the resulting
continuous triangle with the configured coverage-threshold policy.

### Line

### SRD-compatible intent

A line begins at a point of origin and extends along a chosen direction with a defined width
and length.

### Project decision

Lines should share the same continuous-direction and rasterization framework as cones rather
than introducing a separate ad hoc grid rule.

### Current state

The implementation now treats a line as a continuous 1-cell-wide rectangle cast along an
arbitrary 2D aim vector and rasterizes it with the configured coverage-threshold policy.

### Cube

### SRD-compatible intent

A cube has a point of origin on one of its faces and extends outward from that origin with
its full side length.

### Project decision

Cubes belong to the directional-shape family because the face placement depends on chosen
direction, even though the resulting footprint is not line-like.

### Current state

The implementation now treats a cube as a continuous square projected outward from the point
of origin along an arbitrary 2D aim vector and rasterizes it with the configured
coverage-threshold policy.

### Project note

This is still a 2D-only approximation of the tabletop concept. It does not model vertical
placement.

### Sphere / radius

### SRD-compatible intent

A point is chosen, then a circular or spherical area is formed around it.

### Project note

On a square grid, this will also ultimately depend on the same rasterization policy, even if
an early implementation uses a simpler square-distance approximation.

### Cylinder

### SRD-compatible intent

A point is chosen, then a circular area is formed around that point. In a full 3D rules
context the shape also has height, but this project currently ignores height.

### Project decision

Within our 2D-only system, cylinders are treated like non-directional circular areas for
targeting and rasterization purposes.

### Cube

### SRD-compatible intent

A point of origin is chosen according to the shape's rules and the cube occupies a continuous
volume or area in space.

### Project note

Cube placement rules should use the same geometry-first approach rather than directly
building grid templates.

### Project decision

Within our system, cubes are treated as directional shapes because their placement depends on
an oriented origin rather than only a center point.

### Emanation

### SRD-compatible intent

An emanation originates from a creature or object and moves with that source.

### Project note

Emanations should reuse the same shape generation and filtering pipeline, but with their
origin attached to a moving entity.

## Encounter Integration

### Current direction

The encounter layer should consume rasterized AoE output in this shape:

- origin
- shape type
- affected cells

Then later:

- cover and line-of-effect filters trim the cell set
- creatures in remaining cells become candidate targets
- spell rules decide who is actually affected

### Project decision

AoE event payloads should expose area metadata so the UI and debugging tools can inspect what
the system decided.

## Current Status

The project currently has:

- a backend geometry module
- a rasterized `origin + cells` representation
- an initial cone implementation for `Color Spray`
- an 8-direction approximation for cone facing

This is a valid intermediate state, but not the final geometry model.

The current 8-direction approach is especially temporary for directional shapes. The
long-term model should allow arbitrary continuous direction while still keeping the system
strictly two-dimensional.

## Next Steps

1. Keep documenting AoE behavior in SRD-rule versus project-decision form.
2. Replace 8-direction cone facings with continuous aim input.
3. Choose and document a rasterization policy.
4. Add total-cover filtering on top of the rasterized cell set.
5. Extend the same geometry pipeline to line, sphere, cube, and emanation shapes.
