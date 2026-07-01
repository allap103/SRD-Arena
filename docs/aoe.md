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
6. Map surviving cells to actors.
7. Apply spell- or effect-specific inclusion and exclusion rules.

### Project decision

The main internal representation should be:

- continuous shape information for the geometry layer
- `origin + affected cells` for the rasterized encounter layer

This keeps geometry, cover filtering, and target selection separated.

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

Pros:

- simple to reason about
- generous to players
- easy to explain visually

Cons:

- may produce larger areas than expected
- can make narrow cones and lines feel too wide

### Candidate policy B: majority-cell

Only squares with more than 50 percent coverage are included.

Pros:

- closer to the visible body of the shape
- reduces edge inflation

Cons:

- harder to compute and explain
- can create unintuitive borderline exclusions

### Project decision needed

Before expanding AoE support much further, we should choose one rasterization policy and
apply it consistently across cones, lines, and other partial-cell shapes.

## Shape-Specific Notes

### Cone

### SRD-compatible intent

A cone begins at a point of origin and extends outward in a chosen direction as a continuous
shape.

### Project decision

The final cone system should be aimed by direction vector or aim point, not only by one of
8 named grid facings.

### Current temporary simplification

The current implementation uses 8-direction grid facings as a stepping stone.

### Line

### SRD-compatible intent

A line begins at a point of origin and extends along a chosen direction with a defined width
and length.

### Project decision

Lines should share the same continuous-direction and rasterization framework as cones rather
than introducing a separate ad hoc grid rule.

### Sphere / radius

### SRD-compatible intent

A point is chosen, then a circular or spherical area is formed around it.

### Project note

On a square grid, this will also ultimately depend on the same rasterization policy, even if
an early implementation uses a simpler square-distance approximation.

### Cube

### SRD-compatible intent

A point of origin is chosen according to the shape's rules and the cube occupies a continuous
volume or area in space.

### Project note

Cube placement rules should use the same geometry-first approach rather than directly
building grid templates.

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
- actors in remaining cells become candidate targets
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

## Next Steps

1. Keep documenting AoE behavior in SRD-rule versus project-decision form.
2. Replace 8-direction cone facings with continuous aim input.
3. Choose and document a rasterization policy.
4. Add total-cover filtering on top of the rasterized cell set.
5. Extend the same geometry pipeline to line, sphere, cube, and emanation shapes.
