# Configurable terminal rewards

Training YAML has a `reward` section. These are the defaults in both example
configs (`single_encounter.yaml` and `goblin_pressure.yaml`):

```yaml
reward:
  win: 1.0
  loss: -1.0
  draw: 0.0
  truncation: 0.0
  party_member_down: -0.4
  victory_health: 0.1
  victory_spell_slots: 0.05
  victory_class_resources: 0.0
```

The final score is the selected outcome weight, plus `party_member_down` times
how many distinct starting party members fell from positive HP to 0, plus the
three preservation terms on victory. Intermediate steps receive zero reward.
Falls are remembered even if a creature recovers, counted once per creature,
and include the controlled warlock and scripted allies. They count on losses,
draws and truncations too. A truncated encounter can therefore have a negative
score even when `truncation` is zero.

Each preservation term is its weight multiplied by a fraction between zero and
one for the starting party:

| Term | Fraction at episode end |
| --- | --- |
| `victory_health` | Sum of remaining HP / sum of maximum HP; temporary HP excluded |
| `victory_spell_slots` | Remaining slots / maximum slots, summed across slot levels |
| `victory_class_resources` | Remaining uses / maximum uses, summed across `feature_uses` pools such as Lucky and Rage |

Fractions use the final snapshot's maximum capacities, are clamped to [0, 1],
and are zero when the family has no capacity. Slot levels and class-resource
uses are counted as units, not assigned different tactical values. These terms
measure remaining capacity, including any recovery during the encounter; they
are not a cumulative cost for using abilities. Other resource kinds are not
included in the class-resource term.

With the defaults, a victory with half the party's combined maximum HP remaining,
all spell slots spent, and one party member having fallen scores
`1 - 0.4 + 0.1 * 0.5 = 0.65`. Preserving all spell slots would add another 0.05.
A two-member party wipe scores `-1 - 2 * 0.4 = -1.8`.

To reduce the emphasis on slot preservation, use a smaller weight, for example
`victory_spell_slots: 0.02`. To reproduce win/loss-only scoring, set all four
secondary weights to zero. Omitted fields use their defaults; unknown keys,
nonfinite values, strings and incorrect signs are rejected. Win/preservation
weights are nonnegative, loss/down weights nonpositive, and draw/truncation
weights may have either sign. Keep secondary terms small if winning should
remain the priority; arbitrary weights can make a win score below a loss.

Reward computation uses engine snapshots for the starting party and incremental
defeat events. It runs independently of trace logging and observation filters.
It does not add privileged information to the model's encoded input. This is
still an undiscounted terminal-return learner: weights change the episode
objective, not the timing of credit assigned to individual actions.

## Inspecting and resuming

`config.json`, the run manifest, and checkpoint training settings record the
resolved weights. `metrics.jsonl` and `combat-summary.jsonl` contain the weighted
`reward_components`, their total `reward`, the explicit `episode_outcome`, and
`fallen_party_members`. TensorBoard exposes `reward/*` scalars. The inspector
has a Reward components chart. Evaluation reports contain mean components.
Win/loss/draw counts use the actual outcome, never the reward's sign.

The reward schema is `terminal-party-outcome-v2`. Ordinary `--resume` requires
identical weights and reward schema so a run cannot silently switch objectives.
You can split training into any number of runs with unchanged weights. Changing
weights currently requires a new training run; initializing training from old
weights under a new objective remains a separate, unimplemented fine-tuning
workflow.

Older compatible inference checkpoints whose saved config has no `reward`
section retain win/loss-only evaluation and playback scoring. Their old reward
schema cannot resume training under v2. Existing run files are never rewritten.

After editing the YAML, start a fresh run:

```bash
uv run --extra training --extra observability srd-arena-train \
  --config config/training/goblin_pressure.yaml \
  --run-dir runs/goblin-reward-v2 --episodes 100 --device cuda \
  --progress-interval 1 --trace-every 10 --tensorboard
```

Use a new output directory for each run.
