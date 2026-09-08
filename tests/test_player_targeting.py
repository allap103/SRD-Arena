"""Staged selections expose the owner's choices, not enemy private limits."""

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.encounters.encounter_models.decisions import DecisionFrame
from srd_arena.engine.api import (
    ConfirmTargeting,
    SelectAction,
    Session,
    SetResourceAllocation,
)
from srd_arena.engine.targeting_observations import observe_player_targeting


def _session() -> Session:
    session = Session(
        EncounterCatalog().load_encounter("archive/mass_heal_allocation_showcase"),
        seed=42,
    )
    before = session.observe_player("wounded_party")
    assert before.targeting is None
    action = next(a for a in before.action_details if a.kind == "spell" and a.enabled)
    result = session.execute_player(
        "wounded_party", SelectAction(action.id, before.decision.id)
    )
    assert result.accepted
    return session


def test_owner_can_observe_allocate_and_confirm_without_full_state() -> None:
    session = _session()
    before = session.observe_player("wounded_party")
    assert before.targeting is not None
    assert before.targeting.source_id == "mass_heal"
    assert before.targeting.resource_pool_total == 700
    assert session.observe_player("observers").targeting is None
    allocated = session.execute_player(
        "wounded_party", SetResourceAllocation("healer", 200, before.decision.id)
    )
    assert allocated.update is not None
    after = allocated.update.observation
    assert after.targeting is not None
    assert after.targeting.resource_allocations[0].amount == 200
    assert before.targeting.resource_allocations == ()
    assert any(
        a.kind == "confirm_spell_targets" and a.enabled for a in after.action_details
    )
    confirmed = session.execute_player(
        "wounded_party", ConfirmTargeting(after.decision.id)
    )
    assert confirmed.update is not None
    assert confirmed.update.observation.targeting is None


def test_enemy_allocation_limits_are_not_projected() -> None:
    session = _session()
    before = session.observe_player("wounded_party").targeting
    state = session.encounter_state
    assert state is not None
    pending = state.interrupts.pending_spell_cast
    assert pending is not None
    pending.resource_allocation_limits["observer"] = 999
    assert session.observe_player("wounded_party").targeting == before
    pending.resource_allocation_limits["observer"] = 1
    assert session.observe_player("wounded_party").targeting == before


def test_repeated_choices_are_preserved_and_suspended_selection_is_not_active() -> None:
    session = _session()
    state = session.encounter_state
    assert state is not None
    pending = state.interrupts.pending_spell_cast
    assert pending is not None
    pending.selected_target_refs[:] = ["healer", "healer", "guardian"]
    pending.repeat_target_allocations = True
    pending.require_full_target_count = True
    allies = frozenset({"healer", "guardian", "champion", "scout"})
    selection = observe_player_targeting(state, allies)
    assert selection is not None
    assert selection.selected_target_refs == ("healer", "healer", "guardian")
    assert selection.repeat_target_allocations
    assert selection.require_full_target_count
    state.interrupts.decision_stack.append(
        DecisionFrame("nested", "healer", "reaction", "test")
    )
    assert observe_player_targeting(state, allies) is None
    assert pending.selected_target_refs == ["healer", "healer", "guardian"]
