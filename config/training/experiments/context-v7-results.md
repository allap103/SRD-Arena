# Context v7 comparison results, 2026-09-18

The [matched-budget protocol](context-v7.md) completed. Both checkpoints contain
2,500 training episodes. Each received 150 sampled evaluations and 11 greedy
evaluations, with full traces. No further training was launched during analysis.

The richer inputs did not demonstrate improved play in this experiment. Keep
their corrected information semantics, but do not treat this checkpoint as a
performance improvement over the baseline. One training seed per version does
not establish whether the input changes help or hurt learning in general.

| Evaluation | Baseline v5 wins | Candidate v7 wins |
| --- | ---: | ---: |
| Sampled, training combat seed 42 | 100/100 | 98/100 |
| Sampled, combat seeds 43–52 | 50/50 | 49/50 |
| Greedy, combat seeds 42–52 | 11/11 | 11/11 |

The two non-wins on seed 42 reached the 150-decision limit after the Barbarian
fell. The additional-seed non-win was a loss. Additional seeds vary combat
randomness on the same encounter layout, not encounter composition.

## Behavior on the training seed

The following are from the 100 sampled evaluations per checkpoint:

| Measurement | Baseline v5 | Candidate v7 |
| --- | ---: | ---: |
| Mean terminal reward | 1.0878 | 1.0542 |
| Mean rounds | 3.48 | 5.37 |
| Mean model decisions | 20.88 | 29.22 |
| Mean remaining Warlock spell slots | 0.01 | 0.00 |
| Mean recorded friendly spell damage | 4.91 | 5.78 |
| Empty resolved instant damage-area casts / such casts | 21/171 (12.28%) | 18/147 (12.24%) |
| Mean voluntary moves | 8.73 | 12.89 |
| Immediate reversals / consecutive move pairs | 87/539 (16.14%) | 106/733 (14.46%) |

Empty-cast frequency was essentially unchanged. Candidate movement reversals
were slightly less frequent per consecutive move pair, but total movement and
encounter length increased. Neither measure alone establishes tactical quality.
Recorded friendly damage is an event-derived amount, not net HP loss.

Across all 150 sampled candidate episodes, no spell slots remained. In greedy
evaluation across the additional seeds, the candidate did preserve a slot in
one encounter; slot preservation is therefore possible but unreliable.

The seed-42 greedy replay wins in two rounds with full party health and reward
1.1 for both models. Both spend their second Fireball on an explicitly empty
target list. The new model takes 17 decisions versus eight, including repeated
Drop Prone / Stand Up commands. The current terminal reward has no command or
duration cost, so those extra commands do not lower its score in this replay.

## Next experiment

Preserve these checkpoints and hold rewards and observation inputs fixed for
the next comparison. Test lower entropy regularization (for example 0.001
versus the current 0.01) with matched budgets and multiple learner seeds, then
repeat this frozen-checkpoint evaluation. This is a hypothesis about the next
useful experiment, not a finding that lower entropy solves the behavior.

Two mechanisms deserve separate investigation:

- Exploration is over individual candidates. A spell with many aimed choices
  has more entries than a spell with one target. In a read-only probe of the
  candidate's seed-42 greedy trajectory, the round-two decision had 108 Fireball
  candidates sharing about 54.35% probability, versus one Eldritch Blast
  candidate at about 0.0234%. This exposes a severe learned preference in that
  state; it does not isolate candidate multiplicity as its cause. A future
  spell/action-family choice followed by conditional aiming could separate
  these decisions without merging geometrically distinct areas.
- Every command receives the same undiscounted terminal return in the current
  actor/critic update. Winning therefore provides weak guidance about which
  intermediate commands were useful. Credit assignment and a small efficiency
  reward are separate possible experiments, not changes made by this review.

Do not raise the slot reward, change the action architecture, and lower entropy
in the same experiment. Existing `--resume` deliberately requires identical
learning settings; testing new settings requires a fresh run or a separately
implemented explicit warm-start mode. More encounters can follow once we have
measured improvement in useful actions, resource use, and reliability here.

## Artifacts and reproduction

Local detailed artifacts are under `runs/goblin-context-comparison/`:
`protocol.json`, `comparison.json`, `report.md`, and per-group evaluation,
behavior, summary and trace files. `status.json` reports `complete`. The
inspector's Comparisons page discovers `comparison.json` automatically.

| Checkpoint | Source commit | SHA-256 |
| --- | --- | --- |
| `runs/goblin-reward-v2/policy.pt` | `173265e` | `e161eb859d247bdad9462fa1afff7cd3322103a00ee5e0d76046965c3bb42186` |
| `runs/goblin-context-v7/policy.pt` | `f0f4d52` | `a7979d5046224c565de04badc5a841a1107a58b0f4875cb4dc6ca8905851f077` |

The baseline was evaluated with its compatible frozen source archive. Its
checkpoint cannot be loaded by the current v7 encoder. Watch the new model with:

```bash
uv run --extra training srd-arena-watch \
  --run-dir runs/goblin-context-v7 --mode greedy --device cpu
```

Open the inspector with:

```bash
uv run --extra training --extra observability srd-arena-inspect --runs-dir runs
```
