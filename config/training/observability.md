# Inspect training and combat

Install the optional local tools with `uv sync --extra training --extra observability --dev`.

```bash
uv run --extra training --extra observability srd-arena-train \
  --config config/training/goblin_pressure.yaml --run-dir runs/observed-goblins \
  --episodes 10 --device cuda --tensorboard --trace-every 1
uv run --extra observability tensorboard --logdir runs --host 127.0.0.1
```

Open TensorBoard at http://localhost:6006. Select runs to compare. Scalar steps
are cumulative episode numbers, including resumes. Each run writes its own event
files, avoiding collisions when branching from a checkpoint.

Every completed episode writes `metrics.jsonl` and `combat-summary.jsonl`.
`--trace-every 1` saves all detailed episodes; `--trace-every 10` saves episode 1
and cumulative episodes 10, 20, etc. The default zero saves summaries only. Trace
files in `traces/episode-NNNNNN.jsonl` are flushed per command and may contain a
partial episode after interruption. A summary is only written for a finished
rollout/update. Checkpoint completion remains authoritative if later logging fails.

Metrics separate mean policy loss, value loss (including its 0.5 coefficient),
unweighted entropy and gradient norm before clipping. Total loss is policy loss
plus value loss minus entropy coefficient times entropy. Policy loss is not an
accuracy/error percentage. Reward, truncation, rejection counts and timing help
interpret it. TensorBoard's `train/win_rate` is the cumulative mean within the
current run segment; compare fixed-seed evaluation results separately.

Full traces record controlled and scripted commands, including decision actor,
active turn actor, command acceptance/rejection, compact before/after combat state,
and unrestricted engine events. Initial/setup boundaries are labelled separately.
For learned decisions they include selected probability, value estimate, entropy
and the five highest-probability candidates, using the same inference pass that
selected the action. Greedy mode's probability is the policy probability, not a
claim that the greedy controller samples. Baselines have no invented value estimates.

The summaries count command attempts/acceptances/rejections separately from
`spell_cast`/`attack_resolved` events. Multi-stage targeting commands are not spell
casts. `wait_commands` counts accepted waits, not idle turns or declined reactions.
`recorded_attack_damage` sums attack-event damage and is not comprehensive damage
credit (spell damage, overkill, mitigation and persistent effects need their own
interpretation). Dead or inactive creatures remain in the summary.

Acceptance does not imply a hit or effective spell. Failed saves, successful saves,
conditions and spell effects remain explicit in event data; missing outcomes are
not classified as failures. Events keep their original sequence, action and frame
IDs. They can resolve earlier actions or belong to reactors; boundary proximity
and health changes alone do not establish causal attribution. No general invocation
or Counterspell-chain telemetry is invented where the engine has none.

Diagnostics are privileged spectator data. They do not enter the observation
encoder, influence reward, change action availability or provide legal-action
pruning. Additional snapshot reads are not required. Detailed logging does add
serialization and disk work; use sampled traces for long runs.

## Local inspector

```bash
uv run --extra observability srd-arena-inspect --runs-dir runs
```

Open http://localhost:8501. Choose a run, inspect loss/outcome curves, select an
interval and combatants for command totals, then choose an episode and turn.
Expand commands for top alternatives, before/after state, and engine events.
Exact action/frame ID searches show recorded links across command boundaries.
The refresh button reloads live files; an unfinished JSONL tail is ignored.

The inspector reads ancestor logs up to the recorded resume branch point.
Branches remain separate, and a missing parent leaves only the available history.
Older runs still display their metrics even without combat summaries. Run files
remain ordinary local JSON/JSONL; the inspector does not load model weights or
need CUDA. No cloud account or frontend build is required.
