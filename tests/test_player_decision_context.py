"""Interrupt context is owner-only and independent of private resolution data."""

from dataclasses import replace

import pytest

from srd_arena.domain.encounters.encounter_models.decisions import (
    D20RollModifierRequest,
    D20RollOccurrence,
    DecisionFrame,
    DecisionRequest,
    ForcedMovementChoiceRequest,
    GrappleSaveRequest,
    InitiativeSwapRequest,
    LuckyRollOption,
    OpportunityAttackRequest,
    PendingD20RollModifiers,
    PendingMovement,
    RecklessAttackRequest,
    WeaponMasteryRequest,
)
from srd_arena.domain.encounters.encounter_models.resolution import (
    AttackOutcome,
    ParryRequest,
)
from srd_arena.domain.geometry import MovementBudget, MovementCost, Position
from srd_arena.engine.player_decision_observations import observe_player_decision


@pytest.mark.parametrize(
    ("decision_request", "trigger"),
    [
        (GrappleSaveRequest("private", "enemy", "hero", 99), "grapple_save"),
        (InitiativeSwapRequest("hero"), "initiative_swap"),
        (RecklessAttackRequest("private", "hero"), "reckless_attack"),
        (
            ForcedMovementChoiceRequest(
                "private",
                "hero",
                "enemy",
                "away",
                10,
                "repelling_blast",
                "Repelling Blast",
            ),
            "forced_movement",
        ),
        (
            WeaponMasteryRequest(
                "private", "hero", "enemy", "topple", "maul", "Maul", 15
            ),
            "weapon_mastery",
        ),
        (
            OpportunityAttackRequest(
                PendingMovement(
                    "private",
                    "enemy",
                    "right",
                    Position(1, 0),
                    Position(2, 0),
                    MovementBudget(4),
                    MovementCost(1),
                    "private-trigger",
                )
            ),
            "opportunity_attack",
        ),
    ],
)
def test_trigger_context_is_owned_and_filters_participants(
    decision_request: DecisionRequest, trigger: str
) -> None:
    frame = DecisionFrame(
        "decision",
        "hero",
        "choice",
        "private reason",
        can_pass=True,
        request=decision_request,
    )
    context = observe_player_decision(
        frame, allied_refs=frozenset({"hero"}), visible_refs=frozenset({"hero"})
    )
    assert context is not None
    assert context.trigger == trigger
    assert context.can_pass
    assert context.actor_ref in {None, "hero"}
    assert context.target_ref in {None, "hero"}
    assert (
        observe_player_decision(
            frame,
            allied_refs=frozenset({"enemy"}),
            visible_refs=frozenset({"hero", "enemy"}),
        )
        is None
    )


def test_private_dc_and_internal_identity_do_not_change_context() -> None:
    frame = DecisionFrame(
        "frame",
        "hero",
        "grapple_save",
        "private",
        request=GrappleSaveRequest("first", "enemy", "hero", 10),
    )
    before = observe_player_decision(
        frame,
        allied_refs=frozenset({"hero"}),
        visible_refs=frozenset({"hero", "enemy"}),
    )
    frame.request = GrappleSaveRequest("different", "enemy", "hero", 99)
    after = observe_player_decision(
        frame,
        allied_refs=frozenset({"hero"}),
        visible_refs=frozenset({"hero", "enemy"}),
    )
    assert before == after


def test_lucky_describes_the_current_roll_without_exposing_other_occurrences() -> None:
    option = LuckyRollOption(
        "hero",
        D20RollOccurrence("private", "attack_roll", "enemy", "hero", "secret label"),
        "disadvantage",
    )
    pending = PendingD20RollModifiers("private-action", (option,))
    frame = DecisionFrame(
        "frame",
        "hero",
        "d20_roll_modifier",
        "private",
        request=D20RollModifierRequest(pending),
    )
    context = observe_player_decision(
        frame, allied_refs=frozenset({"hero"}), visible_refs=frozenset({"hero"})
    )
    assert context is not None
    assert context.roll_kind == "attack_roll"
    assert context.offered_roll_mode == "disadvantage"
    assert context.actor_ref is None
    assert context.target_ref == "hero"
    pending.options = (replace(option, owner_ref="enemy"),)
    assert (
        observe_player_decision(
            frame, allied_refs=frozenset({"hero"}), visible_refs=frozenset({"hero"})
        )
        is None
    )


def test_parry_omits_private_roll_damage_and_effectiveness() -> None:
    attack = AttackOutcome([], True, 17, 8, False, {"target_ac": 16})
    request = ParryRequest(
        "attack",
        "enemy",
        "hero",
        "Secret",
        "Hero",
        "Secret weapon",
        2,
        attack,
        "Parry",
        2,
        16,
    )
    frame = DecisionFrame("frame", "hero", "parry", "Parry", request=request)
    before = observe_player_decision(
        frame,
        allied_refs=frozenset({"hero"}),
        visible_refs=frozenset({"hero", "enemy"}),
    )
    attack.attack_roll = 99
    attack.damage = 200
    after = observe_player_decision(
        frame,
        allied_refs=frozenset({"hero"}),
        visible_refs=frozenset({"hero", "enemy"}),
    )
    assert before == after
    assert before is not None and before.trigger == "parry"


def test_unknown_requests_fail_closed() -> None:
    frame = DecisionFrame(
        "frame", "hero", "new-kind", "secret", request=DecisionRequest()
    )
    assert (
        observe_player_decision(
            frame, allied_refs=frozenset({"hero"}), visible_refs=frozenset({"hero"})
        )
        is None
    )
