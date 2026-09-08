"""Known spell descriptors survive resource exhaustion and hide enemy sheets."""

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import Session


def test_warlock_catalog_describes_scaled_spells_and_feature_grants() -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    catalog = session.observe_player("heroes").creature("warlock").spell_capabilities
    assert catalog is not None
    assert len({entry.id for entry in catalog}) == len(catalog)
    spells = {entry.spell_id: entry for entry in catalog}
    blast = spells["eldritch_blast"]
    assert blast.maximum_targets == 2
    assert blast.cast_level == 0 and blast.spell_slot_cost == 0
    assert blast.resolution_kind == "attack"
    assert blast.range_kind == "feet" and blast.range_amount == 120
    assert spells["scorching_ray"].cast_level == 3
    assert spells["scorching_ray"].maximum_targets == 4
    assert spells["hold_person"].maximum_targets == 2
    assert spells["hold_person"].concentration
    assert spells["hold_person"].save_ability == "wisdom"
    assert spells["fireball"].maximum_targets is None
    assert spells["fireball"].area_size_feet == 20
    vigor = spells["false_life"]
    assert vigor.grant_id == "fiendish_vigor"
    assert vigor.cast_level == 1 and vigor.spell_slot_cost == 0
    assert vigor.temporary_hit_point_dice == "maximum"


def test_resource_exhaustion_does_not_remove_known_capabilities() -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    before = session.observe_player("heroes").creature("warlock").spell_capabilities
    state = session.encounter_state
    assert state is not None
    casting = state.creatures["warlock"].creature.spellcasting
    assert casting is not None
    for level in casting.spell_slots_remaining:
        casting.spell_slots_remaining[level] = 0
    assert (
        session.observe_player("heroes").creature("warlock").spell_capabilities
        == before
    )


def test_enemy_spell_definition_changes_do_not_change_enemy_row() -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    team = next(team for team in session._read().team_ids if team != "heroes")
    before = session.observe_player(team).creature("warlock")
    assert before.spell_capabilities is None
    state = session.encounter_state
    assert state is not None
    casting = state.creatures["warlock"].creature.spellcasting
    assert casting is not None
    casting.learned_spells.clear()
    casting.attack_bonus = 99
    casting.save_dc = 99
    assert session.observe_player(team).creature("warlock") == before
