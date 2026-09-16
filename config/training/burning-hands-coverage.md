# Burning Hands coverage candidates

The first coverage-aware encoder groups Burning Hands choices by which currently
disclosed living creatures their cones cover. The model chooses among these
groups and separate movement actions. It receives no suggested destination or
hand-written positioning reward.

For each existing integer aim coordinate on the board, an engine helper computes
the cone using the shared runtime geometry, the encounter's overlap threshold,
total-cover ray filtering and occupied creature footprints. A group keeps the
first aim in deterministic row order. These are the combinations reachable by
the existing discrete aim grammar, not every possible continuous orientation.
Only immutable geometry is cached; creature membership is recomputed after every
observation, including movement.

Membership includes current disclosed allies and visible enemies, and excludes
defeated creatures. Hidden or last-known enemies cannot change either the groups
or their representative aims. An empty disclosed group is retained because a
hidden creature might occupy that cone. If current creature position, size or
defeat information, actor position or the permitted cone template is unavailable,
the adapter falls back to the original uncompressed aims with unknown coverage.

Every grouped candidate carries `affected_refs`. The numeric encoder maps these
references into its stable creature slots, producing a candidate-by-entity mask,
a coverage-known flag, and own/ally/enemy counts. The policy scores the candidate
using the mean embedding of its covered creatures alongside the existing inputs.
Known-empty coverage has an empty mask and a true known flag; unsupported coverage
has an empty mask and a false flag. Sampled decision traces include `affected_refs`
for selected candidates and top alternatives.

Coverage means geometric inclusion, not guaranteed damage, failed saves or legal
execution. The real engine validates the selected command. Its existing rejection
of an area cast with no actual targets remains unchanged. In particular, an empty
disclosed group may execute against hidden occupants or be rejected as
`target_unavailable`. No hidden-state probe is used to distinguish those cases.

Fireball, Hypnotic Pattern and Stinking Cloud retain their existing aim choices
and have unknown coverage in this version. Expanding to persistent areas requires
preserving relevant placement distinctions even when current target sets match.

Schema versions are `filtered-observation-v3`, `experimental-candidates-v3`,
`experimental-encoder-v3` and `entity-candidate-actor-critic-v2`. Start a fresh run;
older checkpoints cannot resume with this feature layout. For example:

```bash
uv run --extra training --extra observability srd-arena-train \
  --config config/training/goblin_pressure.yaml \
  --run-dir runs/goblin-coverage-v1 --episodes 10 --device cuda \
  --progress-interval 1 --trace-every 1 --tensorboard
```

Use a new output directory. Ten episodes are a smoke experiment, not evidence
that positioning or tactics have been learned. Compare against the waiting and
random baselines using the [observability tools](observability.md).

Regression tests compare all grouped sets and representative aims with runtime
spell targeting at two overlap thresholds, with total cover and larger creatures.
They also execute non-empty representatives, check ally coverage, hidden/stale
information independence, movement recomputation, missing-information fallback,
entity-mask alignment and the policy's use of covered creature embeddings.
