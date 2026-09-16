# Single-encounter training experiment

This experiment establishes a working observation → decision → game → reward →
parameter-update loop. It deliberately repeats one authored encounter and one
combat seed. It makes no claim of generalization or competent play.

## Run

```sh
uv sync --extra training --dev
uv run --extra training srd-arena-train \
  --config config/training/single_encounter.yaml \
  --run-dir runs/first-experiment --episodes 10 --device auto

uv run --extra training srd-arena-evaluate \
  --run-dir runs/first-experiment --episodes 5 --device auto
```

Each run requires a new output directory. `--device cuda` explicitly requires
working CUDA and fails if it is unavailable. `auto` uses CUDA if this process
can access it, otherwise CPU. `--device cpu` is useful for reproducibility and
small-model comparisons. Device selection tests a real forward/backward
operation. The simulation itself remains Python/CPU code.

### Continue training across runs

New checkpoints contain resumable training state after each completed episode
and its optimizer update. To add 100 episodes to an existing run:

```bash
uv run --extra training srd-arena-train \
  --resume runs/goblin-performance-test \
  --run-dir runs/goblin-performance-continued \
  --episodes 100 --device cuda --progress-interval 1
```

`--resume` reads the source run's frozen configuration and observation policy;
it cannot be combined with `--config`. `--episodes` is required and means
**additional** episodes. The output directory must be new. The source is untouched,
and the output is self-contained for evaluation, playback and further resumes.
Episode numbering continues globally; logs contain only the new episodes, and
the manifest records the parent path and starting/target episode numbers.

The checkpoint restores model weights, Adam state, Python/NumPy/PyTorch random
states and the active CUDA generator state. An interrupted rollout/update resumes
from the previous saved boundary, repeating any work after that boundary. No
mid-encounter state is saved. If checkpoint replacement succeeded before a log
write failed, the checkpoint's completed count is authoritative.

Resume requires matching model/encoder/action/observation/reward schemas, policy,
learning settings and CPU/CUDA device type. Exact reproduction additionally assumes
unchanged game content/code, library versions and hardware behavior. This mode
does not change the encounter or fine-tune with new hyperparameters. Checkpoints
created before training-state support remain usable for compatible evaluation
and playback, but cannot resume training; start a fresh run to produce resumable
checkpoints.

Evaluate the same encounter with `--mode random`, `--mode wait`, or
`--mode greedy`; the default `sample` samples the learned policy with a recorded
sampling seed. These are overfit checks on the saved combat seed, not held-out
evaluation. In this encounter the scripted Barbarian can win without useful
Warlock play, so high party win rate alone does not demonstrate that the Warlock
has learned. The waiting baseline helps expose this limitation.

PyTorch is an optional training dependency. GUI/headless use does not import it.
The encoder uses NumPy arrays, and the learner converts them to tensors on the
selected device. Full development checks and CI install the training extra.

## Watch a saved model

```sh
uv run --extra training srd-arena-watch \
  --run-dir runs/first-experiment --device auto
```

This opens the normal game GUI directly on the checkpoint's saved encounter,
combat seed and observation policy. The model plays the fixed perspective
creature; scripted creatures and interrupts use the same environment as training.
The GUI shows unrestricted spectator information, while inference receives only
the saved filtered encoding. Game-action buttons/clicks cannot override the model.

Use **Pause/Play**, **Step**, **Restart**, and the **Delay** control in the toolbar.
One step resolves one model command or one scripted action, so automatic turns
are visible too. Restart restores both the saved combat seed and sampling seed
and leaves playback paused. Finished/truncated episodes stop automatically;
inference errors stop playback and show their message in the toolbar.

Click **Pop out** beside **Combat Log** to inspect the live log in a separate,
resizable window. Uncheck **Follow new entries** to keep your reading position
while play continues; log text can be selected and copied. Closing the log window
or clicking **Return to sidebar** docks it again without losing history. These
controls are also available during normal interactive play.

Options: `--paused` starts paused, `--delay-ms 500` sets pacing (20–10000 ms),
`--mode sample` (default) or `--mode greedy` chooses the selection rule, and
`--sampling-seed 123` controls stochastic choices. `--device cuda` requires CUDA;
`--device cpu` forces CPU. This runs inference only; it does not train or alter
the checkpoint. Small inference/game steps execute between Qt timer ticks.

The earlier slot-limit checkpoint was trained for 50 CUDA episodes with the 2024
one-slot-per-caster-per-turn rule enforced:

```sh
uv run --extra training srd-arena-watch \
  --run-dir runs/slot-limit-v1 --device cuda
```

It won all five sampled evaluations on the same encounter seed, without
truncation. This remains a single-encounter integration check, not evidence of
general competence. Its audited playback spent one slot on Stinking Cloud in
round 1 and the second in round 2, with no duplicate slot use on a turn.
Evaluation and audit results are saved beside the checkpoint. Local `runs/`
artifacts are ignored by Git; `runs/cuda-smoke` predates the rule correction.

The watch entry point is separate from the JSONL CLI, and normal GUI/headless
launches do not import PyTorch.

## Goblin pressure experiment

`goblin_pressure.yaml` trains on `warlock_goblin_pressure`: the same level-five
Warlock and scripted Barbarian, the three original melee Goblin Warriors, eight
additional Goblin Warriors using the existing archer behavior, and the original
inactive Ogre target. Goblin statistics, hero loadouts and rewards are unchanged.
The 12-by-9 board contains 14 creatures; encoder capacity is raised to 16.

Calibration uses combat seed 42. The idle controller only waits, keeps initiative
and declines interrupts; an unhandled decision raises an error instead of choosing
an arbitrary action. A separate reference controller casts Eldritch Blast at
enemies, confirms targeting and otherwise waits/declines. That reference uses
player-visible spell descriptors absent from the experimental numeric encoding;
it demonstrates that active participation can win, rather than measuring learned
performance under identical inputs.

| Goblins | Added goblins' behavior | Idle warlock | Eldritch Blast reference |
| --- | --- | --- | --- |
| 5, 7, 9, 11 | Melee chase | Win | Win |
| 5, 7, 9 | Archer | Win | Win |
| **11** | **Archer** | **Loss** | **Win** |
| 15, 19, 23 | Archer | Loss | Loss |

These are individual deterministic calibration fights, not win-rate estimates
over combat seeds. The chosen reference victory included damage to goblins; the
idle defeat involved no spell casts. Both outcomes are regression-tested in
`tests/test_goblin_pressure.py`. Local sweep records and the probe script are in
`runs/goblin-calibration/`. The original encounter remains available unchanged.

```sh
uv run --extra training srd-arena-train \
  --config config/training/goblin_pressure.yaml \
  --run-dir runs/goblin-pressure --device cuda
```

The configuration runs 150 episodes from scratch on seed 42, with a 150-decision,
1500-engine-step and 40-round budget per episode. Terminal team wins/losses are
still the only reward. Every completed update atomically replaces `policy.pt`,
whose `completed_episodes` metadata distinguishes partial runs from complete
ones. Newly created checkpoints also contain optimizer/RNG state for resume;
historical checkpoints from earlier implementations do not.

The harder encounter exposed a turn-boundary bug: an external creature defeated
by an opportunity attack during its own movement could leave the engine waiting
for input. Such defeated turns now request automatic advancement through the
shared engine, including in normal GUI play.

The completed local run is `runs/goblin-pressure-v3`: 150 CUDA training episodes
(94 wins, 36 losses, 20 decision-limit stops). Its frozen final checkpoint won
**9 of 10 evaluation fights**, with one loss and no truncations, using independent
policy sampling seeds 123–132 and the unchanged combat seed 42. The deterministic
idle baseline lost, with no spell casts or goblin damage. The trained warlock
averaged 32.4 recorded direct damage to goblins and 4.6 spell casts per fight;
the damage statistic excludes the inactive Ogre and does not quantify control
effects. These results measure this one calibrated encounter, not generalization.

```sh
uv run --extra training srd-arena-watch \
  --run-dir runs/goblin-pressure-v3 --device cuda
```

`training-summary.json`, `evaluation-summary.json` and
`contribution-evaluation.json` contain the results beside the checkpoint.
`evaluate-contribution.py.txt` records the exact evaluation procedure and can be
run with Python from the repository root. Earlier pressure runs stopped at the
defeated-turn bug and are not the completed model. All 1,626 tests passed after
the scenario, baseline and engine changes.

## Module ownership

- `frontends/rl/actions.py`: decision-local candidate indices → public commands.
- `frontends/rl/encoding.py`: filtered DTOs → versioned numerical arrays.
- `frontends/rl/environment.py`: reset/step, scripted advancement, limits.
- `frontends/rl/rewards.py`: terminal team-outcome reward.
- `training/model.py`: PyTorch shared entity encoder, candidate scorer and critic.
- `training/train.py`, `evaluate.py`: experiment execution and checkpoint replay.
- `training/checkpoint.py`, `playback.py`, `watch.py`: shared checkpoint loading
  and paced model inference, composed with the framework-independent GUI watch
  controls in `frontends/gui/watch.py`.

No domain/engine module imports a learner or numerical framework. RL frontend
modules do not import PyTorch. Training uses the in-process environment; it does
not spawn the game CLI or parse its output. This is a small native reset/step
interface, not a Gymnasium/PettingZoo adapter yet.

## Rewards and time

A party win earns +1, a loss −1, and a draw/truncation 0. Intermediate commands
have zero reward. The learner uses undiscounted terminal return for every
command in the episode and a learned critic baseline. Entropy regularization
encourages exploration; it is not a game resource bonus. Remaining HP, living
allies, slots and resource totals are logged only as terminal diagnostics.

One environment step is one model command attempt. Target selection and
interrupt responses are ordinary decisions. Rejections keep the game state but
consume the model-decision budget. Accepted commands and each automatic action
consume the separate engine-step budget. Limits are checked between automatic
actions, and terminal outcomes take precedence. A configured cutoff is scored
as zero in this finite-horizon experiment; no truncation bootstrapping is used.

Only the fixed perspective creature is externally controlled by the learner.
Scripted turns run until that creature has a decision, including nested
interrupts. A different external decision owner is a setup/scenario error.

## Experimental encoding and action grammar

The encoder exposes structured global, entity and candidate arrays with masks.
Entity slots are assigned once at reset: perspective first, teammates next,
then opponents. IDs only map commands and references; raw creature/action IDs,
labels, private state and experiment metadata do not become numerical features.

Creature features include allegiance, current/stale/unknown indicators,
visibility, known coordinates, exact HP fraction or fractional health interval,
temporary HP/presence, AC, defeat and observed damage, all with explicit missing
value indicators. Selected-target counts and the current actor are included.
Global features include permitted board dimensions, round/sunlight, and active
targeting parameters. Normalization constants and exact feature order are
recorded in the encoder manifest. No normalization uses enemy private maxima.
The board capacity is 24×24; excess entities/candidates produce errors rather
than silent truncation.

Candidates include every currently enabled/available advertised action, integer
cell aims, target add/remove operations, each permitted integer allocation, and
confirm/cancel controls. A public attempt may still fail the real rules; masks
are never computed by probing hidden state. The original decision token stays
attached to each command. Candidate order is not a model feature.

Encoder v2 consumes `config/observations/training.yaml`. Each spell candidate
includes the existing identity/cost/range/save descriptors and numerical summaries
of its `spell-mechanics-v1` tree. Features distinguish outcome branches for damage,
healing, temporary HP and conditions, plus concentration, duration, repeat saves,
ending triggers, movement effects and persistent obscuring areas. Fixed spell and
category vocabularies include unknown buckets. Spell identity supplements mechanics;
it is not inferred from an opaque action token.

The semantic descriptor preserves more detail than the numeric summary. Arbitrary
requirements, choice interactions, custom-rule parameters and contextual feature
modifiers are not fully interpreted numerically. The encoder also omits terrain
channels, appearance/type/size, initiative order, event sequences, optional decision
context and movement directions. Candidates can still collide when only omitted
features differ. It does not yet compute affected-creature coverage or move-and-cast
plans. Aimed actions remain integer cell coordinates. The manifest records feature
order, scales and these limits.

The new descriptor fields and encoder shape require new training. Existing v1
checkpoints (including `runs/goblin-pressure-v3`) are intentionally rejected by
manifest validation; the historical 150-episode results above belong to v1
and are not evidence for this encoder. The pre-change code is saved in commit
`ba20684`. No historical run files are rewritten by this change.

The PyTorch network embeds each creature with shared weights, pools unpadded
rows, and scores candidates using actor/target embeddings, global information,
and candidate parameters. An action mask excludes inadmissible/padded entries.
The critic uses the same permitted state features. A small episodic actor/critic
update uses terminal returns, gradient clipping and Adam; this is not PPO.

## Live episode and turn progress

Training writes readable progress to stderr and preserves completed-episode JSON
records on stdout. Every observed completed initiative turn is logged immediately,
including scripted allies/opponents. Reactions remain part of the active turn.
Defeated initiative slots that are observed being skipped are labelled separately;
cutting an episode short does not mark the unfinished turn complete. The turn
that ends the encounter is labelled accordingly.

```text
Episode 3/150 | 4.2s | engine | round 2 | decisions 12 | engine steps 48
Episode 3/150 | 4.5s | round 2 | Goblin 4 [goblin_4] turn completed | 0.31s | engine steps 3
Episode 3/150 | 8.1s | update | round 4 | decisions 27 | engine steps 106 | samples 12/27
```

Progress defaults to a two-second interval at completed work boundaries. Set it
on the CLI independently of the learning configuration:

```bash
uv run --extra training srd-arena-train \
  --config config/training/goblin_pressure.yaml \
  --run-dir runs/goblin-progress \
  --device cuda --progress-interval 1
```

`--progress-interval 0` disables periodic/stage reports; individual turn messages
remain enabled. `progress.jsonl` stores the flushed structured versions with
`event: progress`, `turn_completed`, or `turn_skipped`. Turn records include round,
creature ID/name, wall duration, episode elapsed time and decision/engine-step
counts during the turn. Round/turn diagnostics may contain spectator information;
they never enter policy observations.

The reporter runs at existing snapshot and learner boundaries without constructing
additional game observations. It is not a background heartbeat during one blocked
engine/CUDA operation. Durations measure wall time between observed boundaries,
including reaction handling and reporting overhead, rather than game-world time.

Completed records in `metrics.jsonl` include `reset_seconds`, `inference_seconds`,
`environment_seconds`, `rollout_seconds`, `update_seconds`, `checkpoint_seconds`,
and `episode_seconds`. Environment time includes engine advancement, observation
projection and encoding. Rollout time includes reset; episode time includes the
update and checkpoint. Initial process/device setup is outside episode timing.
CUDA updates are synchronized before their duration is recorded. The existing
terminal reward and training algorithm are unchanged.

## Environment performance

Immutable spell descriptors and their numeric feature tuples use bounded caches.
Keys include spell definitions, cast levels, grants and casting stats; live action
availability is still checked against current state. A player-turn read also reuses
one candidate/eligibility pass for both executable actions and displayed options.

On this machine, three unprofiled runs of `warlock_goblin_pressure` with seed 42
and the idle controller gave these median reset-through-completion times:

| Implementation | Median encounter time |
| --- | ---: |
| Before these optimizations | 7.01 s |
| Spell descriptor and feature caches | 4.77 s |
| Plus reuse of candidate eligibility within each read | 3.73 s |

All runs had 49 decisions, 228 engine steps and the same loss outcome. Every
encoded policy array at every decision matched byte for byte. This is about 47%
less environment execution time, measured with progress logging disabled and
without model inference or gradient updates; it is not a full-training speedup
measurement. Observation/action schemas and numerical outputs are unchanged by
these optimizations. Repeated snapshot construction remains a profiling target.

## Artifacts and reproducibility

The ignored `runs/` directory holds:

- `config.json`: resolved experiment settings, including independent combat and
  learner seeds. Observation-policy paths resolve relative to the config file.
- `observation-policy.json`: frozen resolved policy (JSON is valid YAML), used
  again during evaluation even if the original policy file changes.
- `manifest.json`: code/library versions, device, policy digest and schemas.
- `metrics.jsonl`: rewards, completion/truncation, command counts/rejections,
  resource diagnostics and loss for each episode.
- `policy.pt`: model state and schema/policy identity, loaded with
  `weights_only=True`, plus versioned optimizer/RNG state and completed episode
  count for training resume. It does not contain an in-progress simulator state.

Repeated runs use independent fixed combat/learner seeds. Exact reproducibility
is expected only under the same software and device conditions; CPU and CUDA
runs need not have identical samples. Useful PyTorch references are
[CUDA semantics](https://docs.pytorch.org/docs/stable/notes/cuda.html) and
[installation/device verification](https://pytorch.org/get-started/locally/).
