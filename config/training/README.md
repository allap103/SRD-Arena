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
ones. These inference checkpoints do not contain optimizer/RNG state for resume.

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

This first encoder intentionally omits terrain channels, appearance/type/size,
initiative order, event sequences, optional decision context and detailed
capability descriptors. Action kinds have a fixed registry with an unknown
bucket. Different abilities or movement directions with identical encoded
features are indistinguishable to this first model; opaque action IDs are not
parsed to invent missing semantics. Aimed actions use integer cell coordinates;
fractional positioning is outside this experimental discrete action grammar.
These omissions are recorded, not presented as the complete proposed RL schema.

The PyTorch network embeds each creature with shared weights, pools unpadded
rows, and scores candidates using actor/target embeddings, global information,
and candidate parameters. An action mask excludes inadmissible/padded entries.
The critic uses the same permitted state features. A small episodic actor/critic
update uses terminal returns, gradient clipping and Adam; this is not PPO.

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
  `weights_only=True`. This is an inference checkpoint, not a training-resume
  snapshot of optimizer, RNG or simulator state.

Repeated runs use independent fixed combat/learner seeds. Exact reproducibility
is expected only under the same software and device conditions; CPU and CUDA
runs need not have identical samples. Useful PyTorch references are
[CUDA semantics](https://docs.pytorch.org/docs/stable/notes/cuda.html) and
[installation/device verification](https://pytorch.org/get-started/locally/).
