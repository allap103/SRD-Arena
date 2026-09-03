"""Exercise shared forced movement and the Repelling Blast decision flow."""

from pathlib import Path

from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.creatures import Attributes, Creature, Equipment, Inventory
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.effects.results import (
    ActionResolutionResult,
    SpellResolutionDetails,
)
from srd_arena.domain.encounters import (
    EncounterBehavior,
    EncounterDefinition,
    EncounterOrchestrator,
    TerrainCell,
    TerrainTraversal,
)
from srd_arena.domain.encounters.actions.feature_runtime.repelling_blast import (
    resolve_repelling_blast_hits,
)
from srd_arena.domain.encounters.actions.forced_movement_choices import (
    forced_movement_actions,
    forced_movement_request,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import (
    ForcedMovementSelection,
)
from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.forced_movement import apply_forced_movement
from srd_arena.domain.encounters.grappling_state import apply_grapple
from srd_arena.domain.geometry import Grid, MovementBudget, MovementCost, Position
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import is_spell_action, use_deterministic_dice

WARLOCK_ENCOUNTER = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)
ORCHESTRATOR = EncounterOrchestrator()
DEFAULT_SOURCE_POSITION = Position(0, 1)
DEFAULT_TARGET_POSITION = Position(2, 1)


def _creature_state(
    creature_id: str,
    position: Position,
    *,
    size: str = "M",
) -> EncounterCreatureState:
    creature = Creature(
        creature_id,
        creature_id.title(),
        "",
        Inventory(),
        Attributes(20, 1, 10, 10, 10, 10, 10, 10, 10),
        Equipment(),
        size=size,
    )
    return EncounterCreatureState(
        creature_id,
        creature,
        position,
        EncounterBehavior("wait"),
        movement_remaining=MovementBudget(4),
        movement_spent_this_turn=MovementCost(2),
    )


def _state(
    *,
    source: Position = DEFAULT_SOURCE_POSITION,
    target: Position = DEFAULT_TARGET_POSITION,
    target_size: str = "M",
    terrain: tuple[TerrainCell, ...] = (),
    blocker: Position | None = None,
) -> EncounterState:
    creatures = {
        "source": _creature_state("source", source),
        "target": _creature_state("target", target, size=target_size),
    }
    if blocker is not None:
        creatures["blocker"] = _creature_state("blocker", blocker)
    return EncounterState(
        "forced",
        EncounterDefinition("forced", Grid(12, 8), terrain=terrain),
        creatures,
    )


def test_forced_movement_ignores_speed_and_difficult_terrain_cost() -> None:
    state = _state(
        terrain=(TerrainCell(Position(3, 1), traversal=TerrainTraversal.DIFFICULT),)
    )
    target = state.creatures["target"]

    result = apply_forced_movement(state, "source", "target", "away", 2)

    assert result.path == (Position(3, 1), Position(4, 1))
    assert result.blocked is False
    assert target.position == Position(4, 1)
    assert target.movement_remaining == 4
    assert target.movement_spent_this_turn == 2


def test_forced_movement_stops_before_blocked_terrain() -> None:
    state = _state(
        terrain=(TerrainCell(Position(4, 1), traversal=TerrainTraversal.BLOCKED),)
    )

    result = apply_forced_movement(state, "source", "target", "away", 2)

    assert result.path == (Position(3, 1),)
    assert result.blocked is True
    assert state.creatures["target"].position == Position(3, 1)


def test_forced_movement_checks_the_complete_large_footprint() -> None:
    state = _state(
        target_size="L",
        terrain=(TerrainCell(Position(5, 1), traversal=TerrainTraversal.BLOCKED),),
    )

    result = apply_forced_movement(state, "source", "target", "away", 2)

    assert result.path == (Position(3, 1),)
    assert state.creatures["target"].position == Position(3, 1)


def test_forced_movement_stops_before_an_occupied_space() -> None:
    state = _state(blocker=Position(4, 1))

    result = apply_forced_movement(state, "source", "target", "away", 3)

    assert result.path == (Position(3, 1),)
    assert result.blocked is True


def test_forced_movement_can_pull_a_target_toward_its_source() -> None:
    state = _state(target=Position(4, 1))

    result = apply_forced_movement(state, "source", "target", "toward", 2)

    assert result.path == (Position(3, 1), Position(2, 1))
    assert state.creatures["target"].position == Position(2, 1)


def test_forced_movement_ends_a_grapple_after_separation() -> None:
    state = _state(source=Position(0, 1), target=Position(3, 1))
    state.creatures["grappler"] = _creature_state("grappler", Position(2, 1))
    applied = build_applied_condition(
        condition=Condition.GRAPPLED,
        source_ref="grappler",
        source_label="Grappler",
        target_ref="target",
    )
    assert apply_grapple(state, applied).accepted

    result = apply_forced_movement(state, "source", "target", "away", 1)

    assert result.ended_grapples == (("grappler", "target"),)
    assert state.relationships == []
    assert state.conditions == []


def test_repelling_blast_opens_one_push_choice_for_each_hit() -> None:
    session = Session(load_encounter_directory(WARLOCK_ENCOUNTER))
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("warlock")
    state.creatures["warlock"].position = Position(2, 3)
    state.creatures["ogre_target"].position = Position(6, 3)
    state.creatures["barbarian"].position = Position(0, 7)
    state.creatures["goblin_1"].position = Position(10, 0)
    state.creatures["goblin_2"].position = Position(10, 1)
    state.creatures["goblin_3"].position = Position(10, 2)
    use_deterministic_dice(
        session,
        die_roller=lambda sides: 15 if sides == 20 else 3,
    )

    initial = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "eldritch_blast", target_ref="ogre_target")
    )
    ORCHESTRATOR.submit(state, initial)
    add_second_beam = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target"
        and action.value == "ogre_target"
        and action.id.endswith("-add")
    )
    ORCHESTRATOR.submit(state, add_second_beam)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )

    cast = ORCHESTRATOR.submit(state, confirm)

    assert cast.paused_for_decision is True
    assert [frame.kind for frame in state.interrupts.decision_stack] == [
        "forced_movement",
        "forced_movement",
    ]
    assert forced_movement_request(state.current_decision()).occurrence_index == 1
    assert len([event for event in cast.events if event.type == "decision_opened"]) == 2

    observed_push = next(
        action
        for action in session.observe().scene.action_details
        if action.kind == "forced_movement_choice"
        and action.movement_distance_feet == 10
    )
    assert observed_push.target_ref == "ogre_target"
    assert observed_push.source_id == "repelling_blast"
    push = next(
        action
        for action in forced_movement_actions(state)
        if isinstance(action.value, ForcedMovementSelection)
        and action.value.distance_feet == 10
    )
    moved = ORCHESTRATOR.submit(state, push)

    assert state.creatures["ogre_target"].position == Position(8, 3)
    movement_event = next(
        event for event in moved.events if event.type == "forced_movement_resolved"
    )
    assert movement_event.data["source_id"] == "repelling_blast"
    assert movement_event.data["moved_distance_feet"] == 10
    assert forced_movement_request(state.current_decision()).occurrence_index == 2

    decline = next(
        action
        for action in forced_movement_actions(state)
        if isinstance(action.value, ForcedMovementSelection)
        and action.value.distance_feet == 0
    )
    ORCHESTRATOR.submit(state, decline)

    assert state.interrupts.decision_stack == []
    assert state.current_decision().kind == "turn"


def test_repelling_blast_does_not_offer_a_push_for_a_huge_target() -> None:
    session = Session(load_encounter_directory(WARLOCK_ENCOUNTER))
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = state.creatures["warlock"].creature
    target = state.creatures["ogre_target"].creature
    target.size = "H"
    assert caster.spellcasting is not None
    spell = next(
        spell
        for spell in caster.spellcasting.learned_spells
        if spell.id == "eldritch_blast"
    )
    result = ActionResolutionResult(
        "eldritch_blast",
        "Eldritch Blast",
        [],
        [],
        details=SpellResolutionDetails(
            "ogre_target",
            "Training Ogre",
            (("ogre_target", "Training Ogre"),),
            ("ogre_target",),
            None,
            0,
            0,
            attack_roll_details=({"hit": True, "target_ref": "ogre_target"},),
        ),
    )
    progress = EncounterProgress()

    resolve_repelling_blast_hits(
        state,
        caster=caster,
        spell=spell,
        caster_ref="warlock",
        action_id="cast-1",
        result=result,
        progress=progress,
    )

    assert state.interrupts.decision_stack == []
    assert progress.paused_for_decision is False
