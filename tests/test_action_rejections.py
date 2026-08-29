"""Exercise the shared execution-time action rejection contract."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest

from srd_arena.domain.creatures import Creature
from srd_arena.domain.creatures.feature_actions import FeatureActionDefinition
from srd_arena.domain.encounters.actions.creature_actions.lifecycle import (
    begin_action_execution,
)
from srd_arena.domain.encounters.actions.creature_actions.standard import (
    execute_standard_action,
)
from srd_arena.domain.encounters.actions.eligibility_rules.models import (
    ActionEligibility,
    EligibilityFailure,
)
from srd_arena.domain.encounters.actions.execution import resolve_grapple_action
from srd_arena.domain.encounters.actions.features import resolve_feature_action
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.decisions import DecisionFrame
from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
from srd_arena.domain.geometry import Position


@pytest.mark.parametrize(
    ("reason_code", "message"),
    [
        ("actor_defeated", "A defeated creature cannot act."),
        ("target_unavailable", "The target is not available."),
        ("target_out_of_range", "The target is out of range."),
        ("resource_spent", "No uses remain."),
    ],
)
def test_lifecycle_rejections_publish_messages_and_events(
    reason_code: str,
    message: str,
) -> None:
    """Every stale eligibility category uses the shared rejection shape."""

    failure = EligibilityFailure(reason_code, message, ("effect-1",))
    state = SimpleNamespace(
        creatures={"hero": object()},
        combat_rules=SimpleNamespace(
            action_eligibility=lambda *args: ActionEligibility((failure,))
        ),
        action_sequence=1,
        event_sequence=1,
    )
    context = begin_action_execution(
        cast(EncounterState, state),
        EncounterAction("Act", "attack", creature_ref="hero"),
        DecisionFrame("turn-hero", "hero", "turn", "normal_turn"),
    )

    assert context.rejection is not None
    assert context.rejection.reason_code == reason_code
    assert context.progress.messages[-1] == ("system", message)
    event = context.progress.events[-1]
    assert event.type == "action_resolved"
    assert event.data == {
        "selected_action_id": "",
        "action_value": None,
        "failure_codes": [reason_code],
        "provider_state_ids": ["effect-1"],
        "kind": "attack",
        "success": False,
        "reason_code": reason_code,
        "reason": message,
    }


def test_unimplemented_feature_rejection_retains_feature_identity() -> None:
    """A registered feature without a rule reports an explicit implementation gap."""

    definition = FeatureActionDefinition(
        "mystery",
        "Mystery Feature",
        "bonus_action",
        "self",
        "missing_resolver",
    )
    creature = SimpleNamespace(
        combat_profile=SimpleNamespace(feature_actions={"mystery": definition}),
        feature_uses_remaining={"mystery": 1},
    )
    state = SimpleNamespace(
        current_decision=lambda: SimpleNamespace(creature_ref="hero"),
        active_bonus_action_available=True,
        event_sequence=1,
        dice=SimpleNamespace(roll_die=lambda sides: sides),
        combat_rules=SimpleNamespace(
            apply_healing=lambda *args: 0,
        ),
    )
    progress = EncounterProgress()

    with patch(
        "srd_arena.domain.encounters.actions.features._resolve_feature_action_impl",
        return_value=None,
    ):
        resolve_feature_action(
            cast(EncounterState, state),
            cast(Creature, creature),
            "mystery",
            progress,
            "action-1",
        )

    assert progress.events[-1].data["reason_code"] == "feature_unimplemented"
    assert progress.events[-1].data["feature_id"] == "mystery"
    assert progress.events[-1].data["feature_name"] == "Mystery Feature"


def test_grapple_rejection_records_a_target_that_became_unavailable() -> None:
    """A vanished grapple target produces an event as well as a message."""

    state = SimpleNamespace(
        current_decision=lambda: SimpleNamespace(creature_ref="hero"),
        creatures={
            "hero": SimpleNamespace(
                actions_remaining=1,
                attacks_remaining=0,
                position=Position(0, 0),
            ),
            "goblin": SimpleNamespace(
                is_alive=False,
                position=Position(1, 0),
            ),
        },
        event_sequence=1,
    )
    progress = EncounterProgress()

    resolve_grapple_action(
        cast(EncounterState, state),
        cast(Creature, SimpleNamespace()),
        EncounterAction("Grapple Goblin", "grapple", "goblin"),
        progress,
        "action-1",
    )

    assert progress.messages[-1] == (
        "system",
        "The target is no longer available.",
    )
    assert progress.events[-1].data["reason_code"] == "target_unavailable"
    assert progress.events[-1].data["target_ref"] == "goblin"


def test_wake_rejection_records_a_target_that_became_unavailable() -> None:
    """A stale wake action does not consume an Action or silently do nothing."""

    state = SimpleNamespace(
        creatures={
            "hero": SimpleNamespace(
                creature=SimpleNamespace(name="Hero"),
                position=Position(0, 0),
            ),
            "sleeper": SimpleNamespace(
                is_alive=False,
                position=Position(1, 0),
            ),
        },
        event_sequence=1,
        ongoing_effects=[],
    )
    progress = EncounterProgress()

    matched = execute_standard_action(
        cast(EncounterState, state),
        EncounterAction("Wake Sleeper", "wake_spell_target", "sleeper"),
        DecisionFrame("turn-hero", "hero", "turn", "normal_turn"),
        progress,
        "action-1",
    )

    assert matched is True
    assert progress.events[-1].data["reason_code"] == "target_unavailable"
    assert progress.events[-1].data["target_ref"] == "sleeper"
