"""Exact combat resources belong to allies, never enemy observations."""

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import Session


def test_allied_resources_match_shared_projectors_and_remain_snapshots() -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    before = session.observe_player("heroes").creature("warlock")
    state = session.encounter_state
    assert state is not None
    actor = state.creatures["warlock"]
    spellcasting = actor.creature.spellcasting
    assert spellcasting is not None
    assert before.spell_slots is not None and before.spell_slots
    assert before.resource_pools is not None and before.resource_pools
    assert before.concentrating_on == ()
    level = before.spell_slots[0].level
    spellcasting.spell_slots_remaining[level] = 0
    feature_id = next(iter(actor.creature.feature_uses_remaining))
    actor.creature.feature_uses_remaining[feature_id] = 0
    actor.attacks_remaining = 1
    after = session.observe_player("heroes").creature("warlock")
    assert after.spell_slots is not None
    assert (
        next(slot for slot in after.spell_slots if slot.level == level).remaining == 0
    )
    assert before.spell_slots[0].remaining > 0
    assert after.resource_pools is not None
    assert (
        next(
            pool for pool in after.resource_pools if pool.source_id == feature_id
        ).remaining
        == 0
    )
    assert after.attacks_remaining == 1
    privileged = session.observe().encounter
    assert privileged is not None
    full = next(
        creature
        for creature in privileged.creatures
        if creature.creature_ref == "warlock"
    )
    assert after.spell_slots == full.spell_slots
    assert after.resource_pools == full.resource_pools
    assert after.attacks_per_attack_action == full.attacks_per_attack_action


def test_enemy_resource_changes_do_not_change_enemy_row() -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    read = session._read()
    opponent = next(team for team in read.team_ids if team != "heroes")
    before = session.observe_player(opponent).creature("warlock")
    state = session.encounter_state
    assert state is not None
    actor = state.creatures["warlock"]
    assert actor.creature.spellcasting is not None
    for level in actor.creature.spellcasting.spell_slots_max:
        actor.creature.spellcasting.spell_slots_remaining[level] = 0
    for feature_id in actor.creature.feature_uses_remaining:
        actor.creature.feature_uses_remaining[feature_id] = 0
    actor.actions_remaining = 0
    actor.attacks_remaining = 9
    assert session.observe_player(opponent).creature("warlock") == before
    assert before.spell_slots is None
    assert before.resource_pools is None
    assert before.actions_remaining is None
    assert before.attacks_remaining is None
    assert before.attacks_per_attack_action is None
    assert before.concentrating_on is None
