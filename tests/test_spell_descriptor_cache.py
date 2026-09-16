"""Caching immutable spell descriptions must not hide changed spellcasting facts."""

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import Session, SpellCapabilityObservation
from srd_arena.engine.spell_capability_observations import observe_spell_capabilities


def test_cached_descriptors_follow_stats_levels_and_slot_capacity() -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    session.observe()
    state = session.encounter_state
    assert state is not None
    actor = state.creatures["warlock"].creature
    casting = actor.spellcasting
    assert casting is not None

    def spell(spell_id: str, cast_level: int) -> SpellCapabilityObservation:
        """Find the catalog entry for one exact invocation."""
        return next(
            s
            for s in observe_spell_capabilities(actor)
            if s.spell_id == spell_id and s.cast_level == cast_level
        )

    before = spell("fireball", 3)
    casting.spell_slots_remaining[3] = 0
    assert spell("fireball", 3) is before
    casting.save_dc += 2
    after = spell("fireball", 3)
    assert after.save_dc == before.save_dc + 2  # type: ignore[operator]
    cloud = spell("stinking_cloud", 3)
    assert cloud.mechanics != before.mechanics
    casting.ability_modifier += 1
    assert (
        spell("fireball", 3).mechanics["casting_modifier"]
        != after.mechanics["casting_modifier"]
    )
    blast = spell("eldritch_blast", 0)
    actor.attributes.level = 11
    assert spell("eldritch_blast", 0).maximum_targets > blast.maximum_targets  # type: ignore[operator]
    casting.spell_slots_max[4] = 1
    assert spell("fireball", 4).cast_level == 4
    casting.learned_spells.clear()
    assert not any(s.spell_id == "fireball" for s in observe_spell_capabilities(actor))


def test_read_reuses_eligibility_without_changing_executable_actions() -> None:
    # Compare the read against independent domain discovery, including changed
    # live slot balances, which must never be cached as intrinsic spell facts.
    game = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    game.observe()
    state = game.encounter_state
    assert state is not None
    from srd_arena.domain.encounters.encounter_models.decisions import DecisionFrame

    state.interrupts.decision_stack.clear()
    state.turn.index = state.initiative_order.index("warlock")
    state.interrupts.decision_stack.append(
        DecisionFrame("test-turn", "warlock", "turn", "test")
    )
    casting = state.creatures["warlock"].creature.spellcasting
    assert casting is not None
    for slots in (2, 0):
        casting.spell_slots_remaining[3] = slots
        expected = state.available_actions()
        read = game._read()
        assert game._encounter_actions == expected
        enabled = {
            a.id
            for a in read.action_options
            if a.enabled and not a.kind.startswith("system_")
        }
        assert enabled == {a.id for a in expected}
