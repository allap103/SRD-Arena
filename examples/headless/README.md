# Headless replay examples

`wait-commands.jsonl` is a deterministic six-command trace for
`warlock_training`, seed 42, the initial CLI episode and Warlock perspective.
It keeps initiative, declines optional roll changes and waits. Scripted
creatures advance automatically. This is a protocol fixture, not a training
baseline.

```sh
uv run srd-arena --headless --encounter warlock_training --seed 42 \
  --perspective-creature warlock \
  --observation-config config/observations/player.yaml \
  --controller stdin < examples/headless/wait-commands.jsonl
```

The run reaches combat termination. Substitute `visible-health.yaml` or
`hidden-health.yaml` to replay identical commands with different enemy health
disclosure. The decision tokens are specific to this seeded initial episode;
a general controller must read them from each observation.

The three JSON observations were exported from the penultimate stream record
of that command with `--max-steps 4`, using each named policy. They represent
the same combat state and differ in enemy health disclosure. Regenerate them
with the current CLI when the source/output schema or encounter changes.

See [the policy and protocol reference](../../config/observations/README.md)
for supported settings, commands, errors and lifecycle limits. The older
`examples/observations/` files illustrate the full gameplay and legacy player
contracts; these files illustrate `filtered-observation-v1`.
