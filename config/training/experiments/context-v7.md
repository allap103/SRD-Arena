# Controlled comparison of observation inputs

The preserved baseline is `runs/goblin-reward-v2` (encoder v5, 2,500 episodes).
The candidate is `runs/goblin-context-v7` (encoder v7, 2,500 episodes). This is a
bundled movement/context/action-kind change, not separate feature ablations.
One learner seed per version limits conclusions about training variability.

Both train `warlock_goblin_pressure`, combat seed 42, learner seed 7, hidden
width 32, Adam learning rate 0.001, entropy coefficient 0.01, decision limit 150,
engine-step limit 1,500, round limit 40 and CUDA. Both use these reward weights:
win +1, loss -1, draw/truncation 0, first fall per party member -0.4, normalized
victory health +0.1, normalized victory spell slots +0.05, class resources 0.
Traces are sampled every ten episodes; these do not represent every training
turn. Wall time is affected by other workloads and is not the outcome metric.

Baseline evaluation uses an isolated archive of commit `173265e`, including
`src` and `content`, with the original frozen checkpoint and observation policy.
Candidate training uses commit `f0f4d52`. Their domain game-rule trees match.
Existing baseline weights and reports are not overwritten or converted.

Both checkpoints use CPU evaluation, sampling seed 123 (+ episode index), with:

- 100 sampled episodes on combat seed 42.
- Five sampled episodes on each combat seed 43–52.
- One greedy episode on each combat seed 42–52 (repeating a deterministic
  controller on an identical combat seed would not add independent evidence).
- Full traces for all evaluation episodes.

Additional combat seeds vary randomness on the same layout, not encounter
composition or placement. Sampled repetitions measure policy randomness for a
frozen checkpoint; they are not independent training replicas.

`runs/goblin-context-comparison/protocol.json` freezes these choices and the
baseline SHA-256. Evaluation outputs retain the checkpoint SHA-256, completed
training count, sampling/combat seeds and original report data.

Analyze completed reports with:

```bash
uv run --extra training python -m srd_arena.training.behavior_metrics \
  --run-dir runs/goblin-context-comparison/baseline/sample-seed-42 \
  --actor warlock --damage-area-spells burning_hands fireball
```

The instant-damage area spell IDs are selected from the shared spell catalog by
mechanics (declarative area, instant duration, damage effect), then frozen in the
protocol. For this party they are Burning Hands and Fireball. Persistent/control
areas are deliberately not scored as wasted because they initially hit nobody.

Measurements distinguish:

- Outcome, reward, party falls and remaining slots from completed summaries.
- Recorded friendly spell damage, including the caster, from event-derived
  summaries. This is not net HP loss and may omit unattributed persistent damage.
- Empty resolved instant damage-area casts, with an explicitly empty target
  list. Rejected commands, missing target metadata, saves and immunity do not
  become empty casts; later resolutions are attributed by event actor/action ID.
- Immediate reversals between consecutive executed voluntary moves in one
  turn, returning to the prior start. This is a diagnostic proxy; returning can
  be tactically valid. Rates use consecutive move pairs as denominator.

Trace-derived metrics include the traced episode count and retain per-episode
values. Missing traces are not treated as zero behavior. Historical training
curves provide learning context; conclusions should primarily use the paired
frozen-checkpoint evaluation protocol above.
