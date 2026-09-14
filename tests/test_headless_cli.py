"""Run the real CLI protocol and compare disclosure-independent replays."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import SelectAction
from srd_arena.frontends.headless.adapter import HeadlessGameAdapter
from srd_arena.frontends.headless.cli import parse_command
from srd_arena.frontends.headless.serialization import canonical_json

ARGS = [
    "--headless",
    "--encounter",
    "warlock_training",
    "--seed",
    "42",
    "--perspective-creature",
    "warlock",
    "--controller",
    "stdin",
]


def run_cli(
    commands: str = "", *, preset: str = "player", extra: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    """Launch a subprocess whose import hook rejects any Qt/GUI dependency."""
    script = """
import sys
class NoGui:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("PySide6", "srd_arena.frontends.gui")):
            raise AssertionError("Headless CLI imported GUI")
sys.meta_path.insert(0, NoGui())
from srd_arena.main import main
main()
"""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            *ARGS,
            "--observation-config",
            f"config/observations/{preset}.yaml",
            *extra,
        ],
        input=commands,
        text=True,
        capture_output=True,
        timeout=60,
    )


def records(result: subprocess.CompletedProcess[str]) -> list[dict[str, Any]]:
    """Require a successful pure JSONL stream."""
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_eof_is_truncation_and_seeded_stream_is_stable() -> None:
    first = run_cli()
    stream = records(first)
    assert [r["type"] for r in stream] == ["metadata", "observation", "result"]
    assert stream[-1]["truncation_reason"] == "controller_input_ended"
    assert stream[-1]["steps"] == 0
    assert (
        stream[0]["resolved_policy"]["creatures"]["health"]["disclosure"]["enemy"]
        == "interval"
    )
    assert run_cli().stdout == first.stdout


def test_malformed_and_stale_commands_do_not_consume_steps() -> None:
    command = canonical_json(
        {
            "type": "command",
            "command": "select_action",
            "action_id": "bad",
            "expected_decision_id": "stale",
        }
    )
    stream = records(run_cli("not json\n" + command + "\n"))
    assert [r["code"] for r in stream if r["type"] == "error"] == [
        "invalid_command",
        "stale_decision",
    ]
    assert stream[-1]["steps"] == 0
    observations = [r for r in stream if r["type"] == "observation"]
    assert all(r == observations[0] for r in observations)


@pytest.mark.parametrize(
    "data",
    [
        '{"type":"command","command":"select_action","expected_decision_id":null,"action_id":"a"}',
        '{"type":"command","command":"aim_action","expected_decision_id":"d","action_id":"a","x":true,"y":1}',
        '{"type":"command","command":"set_resource_allocation","expected_decision_id":"d","target_ref":"a","amount":1.5}',
        '{"type":"command","command":"cancel_targeting","expected_decision_id":"d","extra":1}',
        '{"type":"command","type":"command","command":"cancel_targeting","expected_decision_id":"d"}',
        '{"type":"command","command":"aim_action","expected_decision_id":"d","action_id":"a","x":NaN,"y":1}',
    ],
)
def test_strict_command_input(data: str) -> None:
    with pytest.raises(ValueError):
        parse_command(data)


@pytest.mark.parametrize(
    "name,payload",
    [
        ("select_action", {"action_id": "action"}),
        ("aim_action", {"action_id": "action", "x": 1, "y": 2}),
        ("change_target", {"target_ref": "target", "remove": False}),
        ("set_resource_allocation", {"target_ref": "target", "amount": 2}),
        ("confirm_targeting", {}),
        ("cancel_targeting", {}),
    ],
)
def test_all_command_shapes(name: str, payload: dict[str, object]) -> None:
    command = parse_command(
        canonical_json(
            {
                "type": "command",
                "command": name,
                "expected_decision_id": "decision",
                **payload,
            }
        )
    )
    assert command.expected_decision_id == "decision"


def test_config_error_precedes_stdout(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("schema_version: true")
    result = run_cli(extra=("--observation-config", str(path)))
    assert result.returncode == 2
    assert result.stdout == ""
    assert "schema_version" in result.stderr


@pytest.fixture(scope="module")
def wait_trace() -> tuple[str, dict[str, Any]]:
    """Generate legal wait decisions, including nested rolls, until defeat."""
    adapter = HeadlessGameAdapter(EncounterCatalog())
    adapter.start_encounter("warlock_training", seed=42)
    lines: list[str] = []
    for _ in range(1000):
        obs = adapter.observe_player("heroes")
        if obs.completion is not None:
            return "\n".join(lines) + "\n", json.loads(canonical_json(obs.completion))
        if obs.requires_automatic_advance:
            adapter.advance_one_player_automatic_action("heroes")
            continue
        actions = [
            a
            for a in obs.action_details
            if a.enabled
            and a.availability == "available"
            and a.required_configuration is None
        ]
        action = next(
            (
                a
                for a in actions
                if a.kind in {"wait", "keep_initiative", "decline_d20_modifier"}
            ),
            actions[0],
        )
        lines.append(
            canonical_json(
                {
                    "type": "command",
                    "command": "select_action",
                    "action_id": action.id,
                    "expected_decision_id": obs.decision.id,
                }
            )
        )
        result = adapter.submit_player(
            "heroes", SelectAction(action.id, obs.decision.id)
        )
        assert result.accepted
    raise AssertionError("Wait controller did not finish within 1000 steps")


def test_replay_modes_have_identical_game_outcomes(
    wait_trace: tuple[str, dict[str, Any]],
) -> None:
    commands, completion = wait_trace
    streams = [
        records(run_cli(commands, preset=p))
        for p in ("player", "visible-health", "hidden-health")
    ]
    results = [stream[-1] for stream in streams]
    assert results[0] == results[1] == results[2]
    assert results[0]["terminated"] and not results[0]["truncated"]
    assert results[0]["termination_reason"] == completion["reason"]
    assert all(not any(r["type"] == "error" for r in stream) for stream in streams)
    observations = [
        [r["observation"] for r in stream if r["type"] == "observation"]
        for stream in streams
    ]
    assert [o["decision"] for o in observations[0]] == [
        o["decision"] for o in observations[1]
    ]
    assert observations[0] != observations[1] != observations[2]


def test_limits_during_automatic_advance(
    wait_trace: tuple[str, dict[str, Any]],
) -> None:
    commands, _ = wait_trace
    steps = records(run_cli(commands, extra=("--max-steps", "4")))
    assert steps[-1]["steps"] == 4
    assert steps[-1]["truncation_reason"] == "step_limit"
    rounds = records(run_cli(commands, extra=("--max-rounds", "1")))
    assert rounds[-1]["truncation_reason"] == "turn_limit"
    assert rounds[-2]["observation"]["round_number"] == 2


def decode_pretty_stream(source: str) -> list[dict[str, Any]]:
    """Read consecutive multiline JSON objects without relying on line framing."""
    decoder = json.JSONDecoder()
    result = []
    while source.strip():
        source = source.lstrip()
        record, end = decoder.raw_decode(source)
        result.append(record)
        source = source[end:]
    return result


def test_pretty_cli_preserves_records_and_errors() -> None:
    commands = "not json\n"
    compact = records(run_cli(commands))
    pretty = run_cli(commands, extra=("--output-format", "pretty"))
    assert pretty.returncode == 0, pretty.stderr
    assert '\n  "type": ' in pretty.stdout
    assert decode_pretty_stream(pretty.stdout) == compact
    assert (
        run_cli(commands, extra=("--output-format", "jsonl")).stdout
        == run_cli(commands).stdout
    )


@pytest.mark.parametrize(
    "output_format,indented", [("auto", True), ("jsonl", False), ("pretty", True)]
)
def test_terminal_auto_format_and_override(output_format: str, indented: bool) -> None:
    from io import StringIO
    from typing import Literal, cast

    from srd_arena.frontends.headless.cli import run_headless

    class TerminalBuffer(StringIO):
        def isatty(self) -> bool:
            return True

    output = TerminalBuffer()
    run_headless(
        catalog=EncounterCatalog(),
        encounter_id="warlock_training",
        perspective_creature="warlock",
        config_path=Path("config/observations/player.yaml"),
        seed=42,
        max_steps=100,
        max_rounds=10,
        stdin=StringIO(),
        stdout=output,
        output_format=cast(Literal["auto", "jsonl", "pretty"], output_format),
    )
    assert ('\n  "type": ' in output.getvalue()) == indented
    assert (
        decode_pretty_stream(output.getvalue())[-1]["truncation_reason"]
        == "controller_input_ended"
    )
