"""Verify the Fiend Warlock's defeat-triggered temporary Hit Points."""

from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.results import (
    ActionResolutionResult,
    DamageApplication,
    SpellResolutionDetails,
)
from srd_arena.domain.encounters.actions.spell_runtime.aftermath import (
    apply_spell_result_consequences,
)
from srd_arena.domain.encounters.defeat import resolve_creature_defeat
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
from srd_arena.domain.geometry import Position
from srd_arena.engine.session import Session

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _state() -> EncounterState:
    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    session._read()
    assert session.encounter_state is not None
    return session.encounter_state


def _defeat(state: EncounterState, creature_ref: str) -> None:
    state.creatures[creature_ref].creature.current_health = 0


def test_warlock_gains_level_plus_charisma_temporary_hp_for_own_defeat() -> None:
    state = _state()
    _defeat(state, "goblin_1")
    progress = EncounterProgress()

    resolved = resolve_creature_defeat(
        state,
        "goblin_1",
        defeated_by_ref="warlock",
        progress=progress,
        action_id="eldritch-blast",
    )

    assert resolved is True
    assert state.creatures["warlock"].creature.temporary_hit_points == 9
    assert [event.type for event in progress.events] == [
        "creature_defeated",
        "feature_triggered",
    ]
    feature_event = progress.events[-1]
    assert feature_event.data == {
        "feature_id": "dark_ones_blessing",
        "feature_name": "Dark One's Blessing",
        "defeated_ref": "goblin_1",
        "defeated_by_ref": "warlock",
        "offered_temporary_hit_points": 9,
        "previous_temporary_hit_points": 0,
        "temporary_hit_points": 9,
    }


def test_nearby_ally_defeat_triggers_but_distant_defeat_does_not() -> None:
    nearby_state = _state()
    nearby_state.creatures["goblin_1"].position = Position(4, 3)
    _defeat(nearby_state, "goblin_1")

    resolve_creature_defeat(
        nearby_state,
        "goblin_1",
        defeated_by_ref="barbarian",
        progress=EncounterProgress(),
    )

    assert nearby_state.creatures["warlock"].creature.temporary_hit_points == 9

    distant_state = _state()
    distant_state.creatures["goblin_1"].position = Position(5, 3)
    _defeat(distant_state, "goblin_1")

    resolve_creature_defeat(
        distant_state,
        "goblin_1",
        defeated_by_ref="barbarian",
        progress=EncounterProgress(),
    )

    assert distant_state.creatures["warlock"].creature.temporary_hit_points == 0


def test_defeat_finalization_is_idempotent() -> None:
    state = _state()
    _defeat(state, "goblin_1")
    progress = EncounterProgress()

    assert resolve_creature_defeat(
        state,
        "goblin_1",
        defeated_by_ref="warlock",
        progress=progress,
    )
    assert not resolve_creature_defeat(
        state,
        "goblin_1",
        defeated_by_ref="warlock",
        progress=progress,
    )
    assert len(progress.events) == 2


def test_spell_aftermath_routes_defeats_through_feature_triggers() -> None:
    state = _state()
    _defeat(state, "goblin_1")
    result = ActionResolutionResult(
        "fireball",
        "Fireball",
        [],
        [],
        details=SpellResolutionDetails(
            "goblin_1",
            "Goblin One",
            (("goblin_1", "Goblin One"),),
            ("goblin_1",),
            None,
            3,
            3,
            damage_applications=(DamageApplication("goblin_1", 10),),
            success=True,
        ),
    )
    progress = EncounterProgress()

    apply_spell_result_consequences(
        state,
        result=result,
        creature_ref="warlock",
        action_id="fireball",
        progress=progress,
    )

    assert state.creatures["warlock"].creature.temporary_hit_points == 9
    assert any(
        event.type == "feature_triggered"
        and event.data["feature_id"] == "dark_ones_blessing"
        for event in progress.events
    )
