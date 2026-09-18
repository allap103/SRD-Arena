# Inspect training and combat

Install the optional local tools with `uv sync --extra training --extra observability --dev`.

```bash
uv run --extra training --extra observability srd-arena-train \
  --config config/training/goblin_pressure.yaml --run-dir runs/observed-goblins \
  --episodes 10 --device cuda --tensorboard --trace-every 1
uv run --extra training --extra observability tensorboard --logdir runs --host 127.0.0.1
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

Each new trace row also has an `outcome` describing what was known at that
boundary: rejected before casting, submitted and awaiting resolution, cast
resolved (possibly with no immediate effect), or cast failed after spending
resources. `accepted` continues to mean command acceptance only. Watch mode
labels spell choices as attempts and reports their resolution separately.
The inspector derives these labels from events, including older traces, and
links later Lucky/interrupt resolutions to the original attempt by engine action
ID. It never identifies a spell as rejected just because it caused no damage.

The empty-area cast fix changes encounter behavior but not the model tensor
schema. Existing compatible checkpoints can still load; old metrics and traces
describe the earlier rules and are not rewritten. Evaluate or train under the
corrected rules before comparing new results with those runs.

For configurable terminal rewards (`terminal-party-outcome-v2`), episode metrics
and combat summaries include `reward_components` and `fallen_party_members`.
TensorBoard has `reward/*` scalars, and the inspector has a Reward components
chart. Outcome charts use `episode_outcome` rather than reward sign; older
win/loss-only records retain the previous sign-based interpretation. See
[reward configuration](rewards.md) for weights and normalization.

Diagnostics are privileged spectator data. They do not enter the observation
encoder, influence reward, change action availability or provide legal-action
pruning. Additional snapshot reads are not required. Detailed logging does add
serialization and disk work; use sampled traces for long runs.

## Local inspector

```bash
uv run --extra training --extra observability srd-arena-inspect --runs-dir runs
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

## Fixed-protocol evaluation

```bash
uv run --extra training --extra observability srd-arena-evaluate \
  --run-dir runs/observed-goblins --output-dir runs/goblin-comparison \
  --compare --episodes 10 --seed 123 --device cuda --trace-every 1 --tensorboard
```

The comparison copies one checkpoint and its frozen configuration/policy into the
new output directory before evaluating sample, greedy, random and wait controllers.
Each controller gets the same combat seed and limits; episode i uses controller
seed `123 + i - 1`, independently of previous episodes. `--encounter-seed` can
explicitly override the saved combat seed for evaluation. These results remain
checks on one encounter, not evidence of held-out generalization.

`comparison.json` contains the aggregate controller reports. Each controller
subdirectory contains `evaluation.json`, per-episode `metrics.jsonl`, combat
summaries and selected traces, all usable in the inspector. Report manifests
record checkpoint SHA-256, cumulative training episode count, seeds and source
metadata. TensorBoard uses `eval/` tags separately from `train/` metrics.
For one controller, use `--mode greedy` (or sample/random/wait) instead of
`--compare`. Existing output directories are rejected.

Reports include wins/losses/draws/truncations, mean rounds/decisions/engine steps,
rejections and per-creature mean command/resource statistics. Spell-damage totals
use each `spell_cast` event's complete `damage_roll_details` list and its explicit
`applied_damage`, separately for allies/enemies where target teams are known.
They do not double-count the legacy first-detail alias and do not infer damage
from nearby health changes. Unrecorded or later persistent effects remain outside
these direct-spell totals. Engine events in the detailed trace remain the source
for exact saves, effects and attribution.

The inspector also exposes traces without a completed summary as unfinished
episodes, and shows comparison tables when `comparison.json` files are present.
Turn ordering follows the observed timeline rather than alphabetical creature order.

Tool references: [PyTorch TensorBoard integration](https://docs.pytorch.org/tutorials/recipes/recipes/tensorboard_with_pytorch.html)
and [Streamlit interactive tables](https://docs.streamlit.io/develop/api-reference/data/st.dataframe).

## Validation and overhead

On 2026-09-16 the full suite passed 1,654 tests, with the CUDA resume test skipped
in the sandbox. A separate GPU check confirmed identical model weights and CUDA
RNG state with/without detailed tracing and TensorBoard. CPU tests also compare
policy arrays, actions, outcomes and trained weights; Streamlit interaction and
both localhost servers were checked.

Three interleaved idle-controller runs per mode on `warlock_goblin_pressure`,
combat seed 42, measured median rollout times of 4.43 s without recording, 4.33 s
with summaries, and 4.65 s with full traces. Summary overhead was within timing
noise; full traces added about 5% in this probe and wrote about 2.5 MB per episode.
All nine runs had identical outcomes (49 decisions, 228 engine steps). These are
simulation/recording measurements without neural inference, optimization or
TensorBoard writes, not estimates of complete training throughput. Long runs
should sample traces according to their storage and inspection needs.

## Complete-cast preparation

The model now assembles targets locally before one engine submission. Traces
attach a `preparation` list to the outer policy decision, recording selected
references, allocations, completion status and (for learned decisions) each
local choice's probability, entropy and top candidate indices. The outer
`selected_probability` describes the initial spell/aim choice, not the joint
probability of the entire cast.

The submitted command contains the final ordered `target_refs` and `allocations`.
Preparation creates no game events and consumes no engine steps or environment
decisions. Its policy inference time is included in inference timing. These local
choices do contribute training samples, so trajectory length can exceed the
number of submitted environment decisions. Actual reaction, D20 modifier and
between-projectile choices remain separate engine decisions.
