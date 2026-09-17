"""Spell logs separate admission, committed casts, effects, and later resolution."""

from typing import Any

from srd_arena.training.command_outcomes import command_outcome


def declaration(
    action_id: str, selected_id: str = "spell-hypnotic_pattern"
) -> dict[str, Any]:
    """Build the attribution fields present in current and legacy event traces."""
    return {
        "type": "action_declared",
        "action_id": action_id,
        "data": {"selected_action_id": selected_id},
    }


def test_legacy_target_failure_is_not_presented_as_a_completed_cast() -> None:
    declared = declaration("action_1")
    failure = {
        "type": "action_resolved",
        "action_id": "action_1",
        "data": {
            "success": False,
            "reason_code": "target_unavailable",
            "reason": "That target is not available.",
        },
    }
    assert (
        command_outcome(
            kind="spell",
            selected_id="spell-hypnotic_pattern",
            rejection=None,
            events=[declared, failure],
        )
        == "rejected before casting: That target is not available."
    )


def test_failed_invocation_after_spending_is_not_called_rejected() -> None:
    events = [
        declaration("action_1"),
        {
            "type": "invocation_start_checked",
            "action_id": "action_1",
            "data": {"allowed": False},
        },
        {
            "type": "action_resolved",
            "action_id": "action_1",
            "data": {
                "reason_code": "slow.somatic_spell_failure",
                "reason": "Gestures too slow.",
                "success": False,
            },
        },
    ]
    assert (
        command_outcome(
            kind="spell",
            selected_id="spell-hypnotic_pattern",
            rejection=None,
            events=events,
        )
        == "cast failed after spending resources: Gestures too slow."
    )


def test_cast_with_no_effect_is_still_a_cast() -> None:
    events = [
        declaration("action_1"),
        {
            "type": "spell_cast",
            "action_id": "action_1",
            "data": {"success": False},
        },
    ]
    assert (
        command_outcome(
            kind="spell",
            selected_id="spell-hypnotic_pattern",
            rejection=None,
            events=events,
        )
        == "cast resolved — no immediate effect"
    )


def test_later_resolution_is_linked_by_runtime_action_not_repeated_choice_id() -> None:
    first, second = declaration("action_1"), declaration("action_2")
    completed = {
        "type": "spell_cast",
        "action_id": "action_1",
        "data": {"success": True},
    }
    history = [first, second, completed]
    assert (
        command_outcome(
            kind="spell",
            selected_id="spell-hypnotic_pattern",
            rejection=None,
            events=[first],
        )
        == "submitted — awaiting spell resolution"
    )
    assert (
        command_outcome(
            kind="spell",
            selected_id="spell-hypnotic_pattern",
            rejection=None,
            events=[first],
            resolution_events=history,
        )
        == "cast resolved"
    )
    assert (
        command_outcome(
            kind="spell",
            selected_id="spell-hypnotic_pattern",
            rejection=None,
            events=[second],
            resolution_events=history,
        )
        == "submitted — awaiting spell resolution"
    )
    assert (
        command_outcome(
            kind="spell",
            selected_id="spell-hypnotic_pattern",
            rejection="stale_decision",
            events=[],
            resolution_events=history,
        )
        == "rejected before casting: stale_decision"
    )
