# Area coverage candidates

Every aimed action retains the existing finite set of integer coordinates:
one aim per board cell. There is no grouping or coverage-based pruning. The model
chooses a coordinate-bearing candidate; it does not output continuous coordinates.
Movement remains a separate decision.

A shared engine helper annotates supported spell areas using an
`AreaTemplateObservation`, with no spell-name checks:

| Placement | Shape | Size | Rasterization |
| --- | --- | --- | --- |
| Directional from caster | Cone, line, cube | Length in squares; line also has width | Encounter overlap threshold |
| Point-centered at aim | Radius | Radius in squares | Touched cells |
| Point-centered at aim | Cube | Side length in squares | Runtime grid-aligned square |

The template comes from permitted allied spell previews and contains only shape,
placement, dimensions and threshold. It contains no preview origin, raw cells or
occupants. Unsupported or hidden templates produce unknown coverage. The shared
runtime builders preserve the caster-center offset for directions, point-area
centering, board clipping and footprint intersection. Total-cover rays originate
at the caster cell for directional areas and at the chosen cell for point areas.
An aim behind a wall or beyond casting range may still be offered; geometric
coverage does not bypass command validation.

Coverage includes current disclosed living allies and visible enemies, excluding
defeated creatures. Hidden and remembered enemies cannot change coverage.
If a current creature's position, size or defeat status is unavailable, coverage
is unknown for that action. Missing caster position also prevents directional
coverage. Public terrain geometry is cached separately from creature membership;
membership is recomputed for every observation, including after movement.

Each annotated candidate carries `affected_refs`. The encoder supplies a
candidate-by-entity mask, a coverage-known flag and own/ally/enemy counts. The
policy pools covered creature embeddings alongside spell mechanics and aim
coordinates. Known-empty coverage has an empty mask and a true known flag;
unavailable coverage has an empty mask and a false flag. Sampled decision traces
retain affected references for the selected candidate and top alternatives.

Burning Hands, Fireball, Hypnotic Pattern and Stinking Cloud all use this path.
For persistent areas, coverage describes initial geometric inclusion, not future
occupants or immediate damage. Placements with equal current coverage remain
distinct. Spell mechanics describe saves, conditions, damage and persistence.
This does not predict successful effects or hidden occupants.

The existing engine rejection of area casts containing no actual targets remains
unchanged: an empty disclosed area can execute against hidden occupants or fail
with `target_unavailable`. The adapter never probes hidden state to distinguish
these cases.

Schemas are `filtered-observation-v4`, `experimental-candidates-v4`,
`experimental-encoder-v4` and `entity-candidate-actor-critic-v2`. The network
shape is unchanged from the first coverage implementation, but its input
semantics and candidate distribution changed. Older checkpoints are rejected;
start a fresh run:

```bash
uv run --extra training --extra observability srd-arena-train \
  --config config/training/goblin_pressure.yaml \
  --run-dir runs/goblin-area-coverage-v1 --episodes 10 --device cuda \
  --progress-interval 1 --trace-every 1 --tensorboard
```

Use a new output directory. Ten episodes are a smoke experiment, not evidence of
learned positioning. Compare against waiting and random controllers through the
[observability tools](observability.md).

Tests compare every aim with runtime targeting for the four encounter spells,
at two overlap thresholds, with total cover and larger footprints. Additional
tests exercise directional shapes under an unfamiliar spell ID, cast execution,
equal-coverage placement retention, hidden/stale independence, missing information,
defeat, terrain changes, movement, candidate limits and coverage tensor routing.
