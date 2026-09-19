from srd_arena.engine.observation_models import (
    ActionObservation,
    ActionReasonObservation,
)
from srd_arena.engine.player_action_observations import player_action_observations


def _target_action(
    *reasons: ActionReasonObservation,
    target_ref: str = "enemy",
) -> ActionObservation:
    return ActionObservation(
        id="select-enemy",
        label="Select enemy",
        kind="toggle_spell_target",
        creature_ref="warlock",
        enabled=not reasons,
        availability="unavailable" if reasons else "available",
        reasons=reasons,
        target_ref=target_ref,
    )


def test_private_target_requirement_does_not_change_public_availability() -> None:
    action = _target_action(
        ActionReasonObservation(
            "target_creature_type_required",
            "The target must be Humanoid.",
        )
    )

    [projected] = player_action_observations(
        (action,),
        visible_creature_refs=frozenset({"enemy"}),
    )

    assert projected.enabled is True
    assert projected.availability == "available"
    assert projected.reasons == ()


def test_public_failure_remains_when_private_failure_is_redacted() -> None:
    action = _target_action(
        ActionReasonObservation("target_out_of_range", "Target is out of range."),
        ActionReasonObservation(
            "target_condition_required",
            "Target must be incapacitated.",
        ),
    )

    [projected] = player_action_observations(
        (action,),
        visible_creature_refs=frozenset({"enemy"}),
    )

    assert projected.enabled is False
    assert projected.availability == "unavailable"
    assert tuple(reason.code for reason in projected.reasons) == (
        "target_out_of_range",
    )


def test_options_for_unseen_targets_are_not_exposed() -> None:
    action = _target_action()

    assert (
        player_action_observations(
            (action,),
            visible_creature_refs=frozenset(),
        )
        == ()
    )
