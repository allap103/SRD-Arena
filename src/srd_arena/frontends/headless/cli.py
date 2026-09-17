"""Qt-free, bounded JSON Lines controller for authored encounters."""

import json
from dataclasses import fields
from importlib.metadata import version
from pathlib import Path
from typing import Literal, TextIO

from pydantic import TypeAdapter

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    FILTERED_OBSERVATION_SCHEMA_ID,
    AimAction,
    CastSpell,
    GameCommand,
    PolicyProjector,
    SelectAction,
)
from srd_arena.frontends.headless.adapter import (
    EpisodeTruncationReason,
    HeadlessGameAdapter,
)
from srd_arena.frontends.headless.config import load_policy, policy_digest
from srd_arena.frontends.headless.serialization import canonical_json, json_value

MAX_COMMAND_CHARS = 65536
_COMMANDS = {
    "select_action": SelectAction,
    "cast_spell": CastSpell,
    "aim_action": AimAction,
}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate command key")
        result[key] = value
    return result


def parse_command(line: str) -> GameCommand:
    """Validate one flat command record without coercion or unknown members."""
    data = json.loads(line, object_pairs_hook=_unique_object)
    if not isinstance(data, dict) or data.pop("type", None) != "command":
        raise ValueError("Expected a command record")
    name = data.pop("command", None)
    if not isinstance(name, str) or name not in _COMMANDS:
        raise ValueError("Unknown command")
    command_type = _COMMANDS[name]
    if set(data) - {f.name for f in fields(command_type)}:
        raise ValueError("Unknown command fields")
    if not isinstance(data.get("expected_decision_id"), str):
        raise ValueError("A decision ID is required")
    return TypeAdapter(command_type).validate_json(canonical_json(data), strict=True)


class HeadlessSetupError(ValueError):
    """Invalid encounter, perspective, or runner settings before streaming."""


def run_headless(
    *,
    catalog: EncounterCatalog,
    encounter_id: str,
    perspective_creature: str,
    config_path: Path,
    seed: int | None,
    max_steps: int,
    max_rounds: int,
    stdin: TextIO,
    stdout: TextIO,
    output_format: Literal["auto", "jsonl", "pretty"] = "auto",
) -> None:
    """Run one episode, counting accepted commands and single automatic actions.

    Metadata and the initial observation precede any controller input. Invalid
    commands are recoverable. EOF truncates; combat completion takes precedence
    over limits. Unexpected failures propagate to the CLI's stderr boundary.
    """
    if output_format not in {"auto", "jsonl", "pretty"}:
        raise HeadlessSetupError("Unknown output format")
    pretty = output_format == "pretty" or (output_format == "auto" and stdout.isatty())
    policy = load_policy(config_path)
    if max_steps < 1 or max_rounds < 1:
        raise HeadlessSetupError("Step and round limits must be positive")
    adapter = HeadlessGameAdapter(catalog)
    try:
        adapter.start_encounter(encounter_id, seed=seed)
    except (KeyError, ValueError) as exc:
        raise HeadlessSetupError(str(exc)) from exc
    snapshot = adapter.observe_gameplay()
    perspective = next(
        (
            c
            for c in snapshot.creatures
            if c.combat.creature_ref == perspective_creature
        ),
        None,
    )
    if perspective is None or not perspective.combat.is_alive:
        raise HeadlessSetupError(
            "Perspective must name a living creature in the encounter"
        )
    team_id = perspective.combat.team_id
    projector = PolicyProjector(policy, perspective_creature)

    def emit(record: object) -> None:
        if pretty:
            stdout.write(
                json.dumps(json_value(record), indent=2, allow_nan=False) + "\n\n"
            )
        else:
            stdout.write(canonical_json(record) + "\n")
        stdout.flush()

    emit(
        {
            "type": "metadata",
            "protocol_version": 1,
            "code_version": version("srd-arena"),
            "source_schema_id": snapshot.schema_id,
            "output_schema_id": FILTERED_OBSERVATION_SCHEMA_ID,
            "policy_schema_version": policy.schema_version,
            "policy_digest": policy_digest(policy),
            "resolved_policy": policy,
            "encounter_id": encounter_id,
            "seed": adapter.seed,
            "perspective_creature_ref": perspective_creature,
            "perspective_team_id": team_id,
            "limits": {"max_steps": max_steps, "max_rounds": max_rounds},
        }
    )
    steps = 0
    while True:
        snapshot = adapter.observe_gameplay()
        observation = projector.project(snapshot)
        if observation.completion is not None:
            emit({"type": "observation", "observation": observation})
            break
        reason = None
        if steps >= max_steps:
            reason = EpisodeTruncationReason.STEP_LIMIT
        elif (
            snapshot.game.encounter is not None
            and snapshot.game.encounter.round_number > max_rounds
        ):
            reason = EpisodeTruncationReason.TURN_LIMIT
        if reason is not None:
            adapter.truncate(reason)
            emit({"type": "observation", "observation": observation})
            break
        if observation.requires_automatic_advance:
            adapter.advance_one_player_automatic_action(team_id)
            steps += 1
            continue
        if not any(
            c.creature_ref == observation.decision.creature_ref
            and c.allegiance != "enemy"
            for c in observation.creatures
        ):
            raise RuntimeError(
                "An external decision belongs to a team without a controller"
            )
        emit({"type": "observation", "observation": observation})
        line = stdin.readline(MAX_COMMAND_CHARS + 1)
        if not line:
            adapter.truncate(EpisodeTruncationReason.CONTROLLER_INPUT_ENDED)
            break
        if len(line) > MAX_COMMAND_CHARS:
            # Discard the rest of this record in bounded chunks before retrying.
            while line and not line.endswith("\n"):
                line = stdin.readline(MAX_COMMAND_CHARS + 1)
            emit(
                {
                    "type": "error",
                    "code": "invalid_command",
                    "message": "Command record is too large",
                }
            )
            continue
        try:
            command = parse_command(line)
        except ValueError, TypeError, RecursionError:
            emit(
                {
                    "type": "error",
                    "code": "invalid_command",
                    "message": "Malformed command record",
                }
            )
            continue
        result = adapter.submit_player(team_id, command)
        if result.failure is not None:
            emit(
                {
                    "type": "error",
                    "code": result.failure.code,
                    "message": "Command rejected; use the current observation",
                }
            )
            continue
        steps += 1
    status = adapter.episode_status()
    emit(
        {
            "type": "result",
            "terminated": status.terminated,
            "truncated": status.truncated,
            "termination_reason": status.termination_reason,
            "truncation_reason": status.truncation_reason,
            "winning_team_id": status.winning_team_id,
            "steps": steps,
        }
    )
