from dataclasses import replace

import pytest

from srd_arena.engine.observations import ActionObservation
from srd_arena.frontends.gui.presentation.models import (
    BattlefieldCreatureView,
    BattlefieldView,
    EncounterView,
    GridPositionView,
    ResourceSummaryView,
)
from srd_arena.frontends.gui.ui.encounter.config import TargetSelectionMode
from srd_arena.frontends.gui.ui.encounter.movement import (
    build_movement_plan,
    movement_plan_is_current,
    shortest_movement_paths,
)
from srd_arena.frontends.gui.ui.encounter.targeting import (
    action_for_target_click,
    cancel_targeting_action,
)


def test_movement_preview_uses_shortest_paths_around_occupied_cells() -> None:
    unobstructed_paths = shortest_movement_paths(
        width=4,
        height=4,
        origin=(0, 0),
        blocked=set(),
        max_steps=2,
    )
    movement_paths = shortest_movement_paths(
        width=4,
        height=4,
        origin=(0, 0),
        blocked={(1, 0)},
        max_steps=2,
    )

    assert unobstructed_paths[(2, 1)] == ("right", "down-right")
    assert movement_paths[(2, 0)] == ("down-right", "up-right")
    assert (1, 0) not in movement_paths
    assert (3, 3) not in movement_paths


def test_movement_plan_uses_active_creature_and_advertised_movement() -> None:
    encounter = _encounter_view()

    plan = build_movement_plan(encounter, "actor")

    assert plan is not None
    assert plan.creature_ref == "actor"
    assert plan.path_to((2, 0)) == ("down-right", "up-right")
    assert plan.path_to((1, 0)) is None
    assert movement_plan_is_current(plan, encounter.battlefield)
    with pytest.raises(TypeError):
        plan.paths[(3, 3)] = ("down-right",)  # type: ignore[index]


def test_movement_plan_rejects_inactive_creature_and_expires_on_turn_change() -> None:
    encounter = _encounter_view()
    plan = build_movement_plan(encounter, "actor")
    assert plan is not None

    actor, blocker = encounter.battlefield.creatures
    changed_battlefield = replace(
        encounter.battlefield,
        creatures=(
            replace(actor, is_active=False),
            replace(blocker, is_active=True),
        ),
    )
    encounter = replace(encounter, battlefield=changed_battlefield)

    assert build_movement_plan(encounter, "actor") is None
    assert not movement_plan_is_current(plan, encounter.battlefield)


def test_target_click_prefers_requested_allocation_direction() -> None:
    mode = TargetSelectionMode(
        kind="toggle_spell_target",
        source_trigger_id="eldritch_blast",
    )
    actions = [
        _target_action("allocation-remove", "remove"),
        _target_action("allocation-add", "add"),
    ]

    assert action_for_target_click(actions, mode, "target") == actions[1]
    assert (
        action_for_target_click(
            actions,
            mode,
            "target",
            remove_allocation=True,
        )
        == actions[0]
    )


def test_cancel_targeting_action_finds_only_explicit_cancellation() -> None:
    ordinary = ActionObservation("attack", "Attack", "attack", "actor")
    cancel = ActionObservation(
        "cancel-targeting",
        "Cancel",
        "cancel_spell_targets",
        "actor",
    )

    assert cancel_targeting_action([ordinary, cancel]) == cancel
    assert cancel_targeting_action([ordinary]) is None


def _encounter_view() -> EncounterView:
    actor = BattlefieldCreatureView(
        creature_ref="actor",
        creature_id="actor",
        name="Actor",
        label="A",
        token_image=None,
        team_color="#000000",
        position=GridPositionView(0, 0),
        health=10,
        is_active=True,
    )
    blocker = BattlefieldCreatureView(
        creature_ref="blocker",
        creature_id="blocker",
        name="Blocker",
        label="B",
        token_image=None,
        team_color="#ffffff",
        position=GridPositionView(1, 0),
        health=10,
    )
    battlefield = BattlefieldView(
        width=4,
        height=4,
        creatures=(actor, blocker),
        summary_text="",
    )
    resources = ResourceSummaryView(
        current_health=10,
        max_health=10,
        action_status="Available",
        bonus_action_status="Available",
        reaction_status="Available",
        attacks_available=1,
        conditions=(),
        spell_slots=(),
        movement_remaining=2,
        movement_total=2,
        movement_remaining_feet=10,
        movement_total_feet=10,
    )
    move = ActionObservation(
        id="move-right",
        label="Move right",
        kind="move",
        creature_ref="actor",
        cost={"movement": 1},
        movement_direction="right",
    )
    return EncounterView(
        narrative_text=None,
        battlefield=battlefield,
        resources=resources,
        movement_actions={"right": move},
        non_movement_actions=(),
        feature_actions=(),
        end_turn_action=None,
        action_pane_title="Actions",
    )


def _target_action(action_id: str, operation: str) -> ActionObservation:
    return ActionObservation(
        id=f"{action_id}-{operation}",
        label=operation.capitalize(),
        kind="toggle_spell_target",
        creature_ref="actor",
        source_trigger_id="eldritch_blast",
        target_ref="target",
    )
