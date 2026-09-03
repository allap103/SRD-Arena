"""Exercise shared forced movement and the Repelling Blast decision flow."""

from collections.abc import Sequence
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
    TerrainCell,
    TerrainTraversal,
)
from srd_arena.domain.encounters.actions.feature_runtime.repelling_blast import (
    resolve_repelling_blast_hit,
)
from srd_arena.domain.encounters.actions.forced_movement_choices import (
    forced_movement_actions,
    forced_movement_request,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.decisions import (
    DecisionFrame,
    ForcedMovementChoiceRequest,
)
from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.forced_movement import apply_forced_movement
from srd_arena.domain.encounters.grappling_state import apply_grapple
from srd_arena.domain.geometry import Grid, MovementBudget, MovementCost, Position
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    choose_advertised_action,
    is_spell_action,
    use_deterministic_dice,
)

WARLOCK_ENCOUNTER = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)
DEFAULT_SOURCE_POSITION = Position(0, 1)
DEFAULT_TARGET_POSITION = Position(2, 1)


class _EldritchBlastSelector:
    """Select the Ogre-targeted Eldritch Blast from public scripted options."""

    def select_action(
        self,
        _state: EncounterState,
        _creature_ref: str,
        actions: Sequence[EncounterAction],
    ) -> EncounterAction:
        return next(
            action
            for action in actions
            if is_spell_action(
                action,
                "eldritch_blast",
                target_ref="ogre_target",
            )
        )


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


def _cast_two_beam_eldritch_blast(
    session: Session,
    target_ref: str,
) -> EngineOutcome:
    state = session.encounter_state
    assert state is not None
    initial = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "eldritch_blast", target_ref=target_ref)
    )
    choose_advertised_action(session, initial)
    add_second_beam = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target"
        and action.value == target_ref
        and action.id.endswith("-add")
    )
    choose_advertised_action(session, add_second_beam)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    return choose_advertised_action(session, confirm)


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


def test_forced_movement_uses_a_pull_label_for_toward_choices() -> None:
    state = _state(target=Position(4, 1))
    state.interrupts.decision_stack.append(
        DecisionFrame(
            "pull-1",
            "source",
            "forced_movement",
            "test",
            request=ForcedMovementChoiceRequest(
                "action-1",
                "source",
                "target",
                "toward",
                10,
                "test_pull",
                "Test Pull",
            ),
        )
    )

    labels = [action.label for action in forced_movement_actions(state)]

    assert "Pull Target (target) 5 ft." in labels


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

    cast = _cast_two_beam_eldritch_blast(session, "ogre_target")

    assert [frame.kind for frame in state.interrupts.decision_stack] == [
        "forced_movement"
    ]
    assert forced_movement_request(state.current_decision()).occurrence_index == 1
    assert len([event for event in cast.events if event.type == "decision_opened"]) == 1
    first_projectile_index = next(
        index
        for index, event in enumerate(cast.events)
        if event.type == "spell_projectile_resolved"
    )
    first_decision_index = next(
        index
        for index, event in enumerate(cast.events)
        if event.type == "decision_opened"
    )
    assert first_projectile_index < first_decision_index

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
        for action in session.read().action_options
        if action.id == observed_push.id
    )
    moved = session.choose(push.id)

    assert state.creatures["ogre_target"].position == Position(8, 3)
    movement_event = next(
        event for event in moved.events if event.type == "forced_movement_resolved"
    )
    assert movement_event.data["source_id"] == "repelling_blast"
    assert movement_event.data["moved_distance_feet"] == 10
    assert forced_movement_request(state.current_decision()).occurrence_index == 2
    second_opened = [event for event in moved.events if event.type == "decision_opened"]
    assert len(second_opened) == 1
    assert second_opened[0].data["occurrence_index"] == 2
    assert [event.type for event in moved.events].index("spell_projectile_resolved") < [
        event.type for event in moved.events
    ].index("decision_opened")

    decline = next(
        action
        for action in session.observe().scene.action_details
        if action.kind == "forced_movement_choice"
        and action.movement_distance_feet == 0
    )
    finished = session.choose(decline.id)

    assert state.interrupts.decision_stack == []
    assert state.current_decision().kind == "turn"
    cast_messages = [*cast.messages, *moved.messages, *finished.messages]
    assert (
        sum("casts Eldritch Blast" in message for _channel, message in cast_messages)
        == 1
    )
    [completed_cast] = [
        event for event in finished.events if event.type == "spell_cast"
    ]
    assert completed_cast.data["projectile_count"] == 2
    assert completed_cast.data["resolved_projectile_count"] == 2
    assert "attack_roll_details" not in completed_cast.data


def test_first_push_can_move_target_out_of_range_of_second_beam() -> None:
    session = Session(load_encounter_directory(WARLOCK_ENCOUNTER))
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.definition.grid = Grid(30, 9)
    state.turn.index = state.initiative_order.index("warlock")
    state.creatures["warlock"].position = Position(0, 3)
    state.creatures["ogre_target"].position = Position(23, 3)
    state.creatures["barbarian"].position = Position(0, 8)
    state.creatures["goblin_1"].position = Position(5, 8)
    state.creatures["goblin_2"].position = Position(7, 8)
    state.creatures["goblin_3"].position = Position(9, 8)
    use_deterministic_dice(
        session,
        die_roller=lambda sides: 15 if sides == 20 else 3,
    )

    first = _cast_two_beam_eldritch_blast(session, "ogre_target")
    push = next(
        action
        for action in session.observe().scene.action_details
        if action.kind == "forced_movement_choice"
        and action.movement_distance_feet == 10
    )

    result = session.choose(push.id)

    assert state.creatures["ogre_target"].position == Position(25, 3)
    assert state.interrupts.decision_stack == []
    skipped = next(
        event for event in result.events if event.type == "spell_projectile_skipped"
    )
    assert skipped.data == {
        "spell_id": "eldritch_blast",
        "projectile_index": 2,
        "target_ref": "ogre_target",
        "reason_code": "target_unavailable",
    }
    projectile = next(
        event for event in first.events if event.type == "spell_projectile_resolved"
    )
    attack_roll_details = projectile.data["attack_roll_details"]
    assert isinstance(attack_roll_details, list)
    assert len(attack_roll_details) == 1
    completed_cast = next(
        event for event in result.events if event.type == "spell_cast"
    )
    assert completed_cast.data["resolved_projectile_count"] == 1
    assert "attack_roll_details" not in completed_cast.data


def test_terminal_hit_waits_for_repelling_blast_before_completing() -> None:
    session = Session(load_encounter_directory(WARLOCK_ENCOUNTER))
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("warlock")
    state.creatures["warlock"].position = Position(2, 3)
    state.creatures["ogre_target"].position = Position(6, 3)
    state.creatures["ogre_target"].creature.current_health = 1
    for target_ref in ("goblin_1", "goblin_2", "goblin_3"):
        state.creatures[target_ref].creature.current_health = 0
    use_deterministic_dice(
        session,
        die_roller=lambda sides: 15 if sides == 20 else 3,
    )

    _cast_two_beam_eldritch_blast(session, "ogre_target")

    assert session.pending_encounter_completion is None
    assert state.current_decision().kind == "forced_movement"
    push = next(
        action
        for action in session.observe().scene.action_details
        if action.kind == "forced_movement_choice"
        and action.movement_distance_feet == 10
    )
    result = session.choose(push.id)

    assert state.interrupts.decision_stack == []
    assert session.pending_encounter_completion is not None
    assert any(event.type == "spell_cast" for event in result.events)


def test_scripted_repelling_blast_uses_maximum_distance_without_a_decision() -> None:
    session = Session(load_encounter_directory(WARLOCK_ENCOUNTER))
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == "warlock"
    )
    participant.controller = "scripted"
    state.definition.grid = Grid(12, 8)
    state.creatures["warlock"].position = Position(2, 3)
    state.creatures["ogre_target"].position = Position(6, 3)
    state.creatures["goblin_1"].position = Position(0, 7)
    state.creatures["goblin_2"].position = Position(2, 7)
    state.creatures["goblin_3"].position = Position(4, 7)
    caster = state.creatures["warlock"].creature
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
            attack_roll_details=(
                {"hit": True, "target_ref": "ogre_target", "projectile_index": 1},
            ),
        ),
    )
    progress = EncounterProgress()

    paused = resolve_repelling_blast_hit(
        state,
        caster=caster,
        spell=spell,
        caster_ref="warlock",
        action_id="cast-1",
        result=result,
        progress=progress,
    )

    assert paused is False
    assert state.creatures["ogre_target"].position == Position(8, 3)
    assert state.interrupts.decision_stack == []
    assert [event.type for event in progress.events] == ["forced_movement_resolved"]


def test_scripted_session_resolves_every_beam_and_maximum_push() -> None:
    session = Session(load_encounter_directory(WARLOCK_ENCOUNTER))
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == "warlock"
    )
    participant.controller = "scripted"
    state._action_selectors["warlock"] = _EldritchBlastSelector()
    state.definition.grid = Grid(16, 9)
    state.turn.index = state.initiative_order.index("warlock")
    state.creatures["warlock"].position = Position(2, 3)
    state.creatures["ogre_target"].position = Position(6, 3)
    state.creatures["barbarian"].position = Position(0, 8)
    state.creatures["goblin_1"].position = Position(3, 8)
    state.creatures["goblin_2"].position = Position(6, 8)
    state.creatures["goblin_3"].position = Position(9, 8)
    use_deterministic_dice(
        session,
        die_roller=lambda sides: 15 if sides == 20 else 3,
    )

    update = session.advance_one_automatic_action()

    assert state.creatures["ogre_target"].position == Position(10, 3)
    assert state.interrupts.decision_stack == []
    assert [event.type for event in update.events].count(
        "spell_projectile_resolved"
    ) == 2
    assert [event.type for event in update.events].count(
        "forced_movement_resolved"
    ) == 2
    [completed_cast] = [event for event in update.events if event.type == "spell_cast"]
    assert completed_cast.data["resolved_projectile_count"] == 2


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

    resolve_repelling_blast_hit(
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
