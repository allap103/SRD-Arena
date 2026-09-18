# Complete spell casts

Adapters assemble casts; the engine validates and resolves them. The domain has
no pending target-selection object and never opens a pre-cast `spell_targets`
frame. Genuine decisions during resolution remain engine-owned.

A `CastSpell` command contains:

- An advertised `action_id` and its `expected_decision_id`. The action fixes the
  spell, cast level, invocation grant and other advertised variant choices.
- Ordered `target_refs`, including repetitions when the spell permits them.
- `allocations`: target/positive-integer pairs for resource-pool spells.
- Optional `aim`: the coordinate or directional aiming point.

The engine validates counts, repetition rules, target eligibility, allocations,
resources and geometry before submitting a complete cast to resolution.
Invalid configuration and stale tokens are rejected without spending resources
or advancing the decision. An accepted invocation can subsequently miss, meet a
successful save, or fail through a spell mechanic. Area coverage remains
geometric inclusion, not a guarantee of successful effects.

A valid area cast with no creatures in its area still spends its normal action
and spell slot. It emits `spell_cast` with empty `target_refs` and null primary
target fields. Instant effects may affect nobody; persistent areas such as
Stinking Cloud are still created and can affect creatures that enter later.
This consumes the caster's slot allowance for the turn. Invalid coordinates,
out-of-range point aims and malformed explicit target selections remain rejected
before casting. Empty-area casting follows the same path for complete commands
and the legacy `AimAction` adapter command.

## GUI

The presenter keeps a local draft over an immutable observation. Adding/removing
targets, allocating resources, refreshing the view or cancelling does not change
game state, random state, history or the engine decision token. A complete fixed
allocation auto-submits; optional target sets and resource allocations can be
confirmed explicitly. A changed engine decision invalidates the draft.

`Session.prepare_spell` is a read-only query used to obtain aim-dependent
configuration choices. The engine remains authoritative when the draft is
submitted. Draft commands live under `frontends/gui`; they are not engine commands.

## ML

Enumerating every full combination of spell, aim and targets grows too quickly
for spells such as Slow. Instead the adapter uses the existing candidate-scoring
policy in a bounded local sequence:

1. Choose an advertised action and aim, including an initial target where the
   action already identifies one.
2. If needed, choose additional targets or resource amounts locally. Additions
   are monotonic: there are no remove/cancel loops. Optional target sets can end
   early; fixed target counts finish automatically when filled.
3. Submit the assembled `CastSpell` once.

There may be several neural-network evaluations for one cast, but only one
engine submission. This uses the same network at each preparation choice;
it does not introduce a separate model or enumerate complete combinations.
All integer AoE placements remain available. When a spell requires explicit
creature selections and admitted information provides no target configuration,
the adapter retains an empty attempt for engine validation without consulting
hidden state. Area spells whose occupants are determined by geometry require
no explicit creature selections.

The encoder includes chosen-target counts, reciprocal-position weights for
ordered sequences, and per-target resource amounts. These are compact summaries,
not a lossless encoding of arbitrary long sequences. They distinguish the
current two-beam assignments, including reversed order. The candidate's coverage
mask remains separate from explicitly selected targets.

Local preparation contributes policy/value training samples. It does not advance
rounds, consume environment decisions, produce game events, or grant the model
additional observations. `prepare_action` finishes a candidate before `step`;
the training, evaluation and playback drivers use this path.

The public configuration DTO is filtered before encoding: hidden targets and
enemy allocation limits do not enter it. Target eligibility is rechecked by the
engine, so a public candidate can still be rejected for private requirements.
Reaction and D20 choices after submission remain normal observed game decisions.

## Compatibility and checks

Current schemas: `filtered-observation-v7`, `experimental-candidates-v6`,
`experimental-encoder-v7`, `entity-candidate-actor-critic-v3`.
Start fresh training; old checkpoints are rejected, not converted or deleted.
The headless protocol now accepts `cast_spell`; the former target-edit,
allocation-edit, confirm and cancel commands have been removed.

Regression coverage includes atomic invalid-cast rejection, GUI cancellation and
submission, ordered beams, resource limits, visibility restrictions, chosen area
targets, model preparation without engine advancement, and preservation of
genuine D20 and between-projectile decisions.
