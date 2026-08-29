from pathlib import Path

import pytest

from srd_arena.application.observations import observe_session
from srd_arena.domain.effects import EffectResult
from srd_arena.domain.effects.application import condition_from_effect
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.grappling_state import apply_grapple
from srd_arena.domain.encounters.participants import creature_controller
from srd_arena.engine.session import Session
from srd_arena.frontends.gui.presentation.session import build_session_presentation
from srd_arena.infrastructure.scenarios import load_scenario_directory
from tests.encounter_runtime_support import (
    choose_advertised_action as _choose_advertised_action,
)
from tests.encounter_runtime_support import (
    use_deterministic_dice as _use_deterministic_dice,
)

TACTICAL_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "tactical_game"
GOBLIN_SKIRMISH_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "full_control_showcase"
)


@pytest.fixture(autouse=True)
def _player_first_initiative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fixed_initiative(self: EncounterState) -> None:
        self.initiative_entries = []
        first_external_ref = next(
            creature_ref
            for creature_ref in self.creatures
            if creature_controller(self, creature_ref) == "external"
        )
        self.initiative_order = [
            first_external_ref,
            *(
                creature_ref
                for creature_ref in self.creatures
                if creature_ref != first_external_ref
            ),
        ]

    monkeypatch.setattr(EncounterState, "roll_initiative", _fixed_initiative)


def _all_external_session() -> Session:
    scenario = load_scenario_directory(
        TACTICAL_SCENARIO_DIR,
        start_scene="goblin_encounter",
    )
    encounter = scenario.encounters["goblin_encounter"]
    for team in encounter.teams:
        team.controller = "external"
    return scenario.create_session()


def _action_id_by_label(session: Session, label: str) -> str:
    return next(
        action.id for action in session.read().action_options if action.label == label
    )


def test_tactical_fixture_loads_explicit_teams() -> None:
    game = load_scenario_directory(
        TACTICAL_SCENARIO_DIR, start_scene="goblin_encounter"
    )
    encounter = game.encounters["goblin_encounter"]

    assert encounter is not None
    assert [(team.id, team.controller) for team in encounter.teams] == [
        ("heroes", "external"),
        ("goblins", "scripted"),
    ]
    assert encounter.teams[1].members == ["goblin_1", "goblin_2", "goblin_3"]


def test_resource_summary_uses_active_creature_movement() -> None:
    session = _all_external_session()
    session.read()
    assert session.encounter_state is not None
    session.encounter_state.active_movement_remaining = 2

    session.choose(_action_id_by_label(session, "Wait"))
    presentation = build_session_presentation(observe_session(session))

    assert presentation.encounter is not None
    assert presentation.encounter.resources.movement_remaining == 6
    assert presentation.encounter.resources.movement_remaining_feet == 30


def test_external_control_pauses_for_each_goblin_turn() -> None:
    session = _all_external_session()
    session.read()
    state = session.encounter_state
    assert state is not None
    starting_position = (
        state.creatures["goblin_1"].position.x,
        state.creatures["goblin_1"].position.y,
    )

    session.choose(_action_id_by_label(session, "Wait"))

    assert state.current_decision().creature_ref == "goblin_1"
    assert (
        state.creatures["goblin_1"].position.x,
        state.creatures["goblin_1"].position.y,
    ) == starting_position
    actions = state.available_actions()
    assert actions
    assert {action.creature_ref for action in actions} == {"goblin_1"}
    assert "Wait" in [action.label for action in actions]
    assert any(action.kind == "move" for action in actions)


def test_externally_controlled_goblin_can_move_then_end_turn() -> None:
    session = _all_external_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    session.choose(_action_id_by_label(session, "Wait"))
    start = (
        state.creatures["goblin_1"].position.x,
        state.creatures["goblin_1"].position.y,
    )
    move = next(action for action in state.available_actions() if action.kind == "move")

    session.choose(
        next(
            action.id
            for action in session.read().action_options
            if action.id == move.id
        )
    )

    assert state.current_decision().creature_ref == "goblin_1"
    assert (
        state.creatures["goblin_1"].position.x,
        state.creatures["goblin_1"].position.y,
    ) != start
    assert state.creatures["goblin_1"].movement_remaining == 5

    session.choose(_action_id_by_label(session, "Wait"))

    assert state.current_decision().creature_ref == "goblin_2"


def test_externally_controlled_goblin_can_attack_opposing_player() -> None:
    session = _all_external_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 2
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2
    _use_deterministic_dice(
        session,
        die_roller=lambda sides: 20 if sides == 20 else 1,
    )
    session.choose(_action_id_by_label(session, "Wait"))

    attack = next(
        action for action in state.available_actions() if action.kind == "attack"
    )

    assert attack.creature_ref == "goblin_1"
    assert attack.value == "player"
    target = state.creatures["player"].creature
    health_before = target.get_health()
    result = session.choose(
        next(
            action.id
            for action in session.read().action_options
            if action.id == attack.id
        )
    )

    assert target.get_health() < health_before
    assert state.current_decision().creature_ref == "goblin_1"
    assert not any(action.kind == "attack" for action in state.available_actions())
    assert any(action.kind == "move" for action in state.available_actions())
    event = next(event for event in result.events if event.type == "attack_resolved")
    assert event.creature_ref == "goblin_1"
    assert event.data["target_ref"] == "player"

    session.choose(_action_id_by_label(session, "Wait"))

    assert state.current_decision().creature_ref == "goblin_2"


def test_secondary_champion_gets_extra_attack_before_turn_ends() -> None:
    session = load_scenario_directory(GOBLIN_SKIRMISH_DIR).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    brynn = state.creatures["champion_2"]
    goblin = state.creatures["red_blade"]
    brynn.position.x = 2
    brynn.position.y = 2
    goblin.position.x = 3
    goblin.position.y = 2
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)
    session.choose(_action_id_by_label(session, "Wait"))

    first_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "attack" and action.value == "red_blade"
    )
    _choose_advertised_action(session, first_attack)

    assert state.current_decision().creature_ref == "champion_2"
    assert brynn.attacks_remaining == 1

    second_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "attack" and action.value == "red_blade"
    )
    _choose_advertised_action(session, second_attack)

    assert state.current_decision().creature_ref == "champion_2"
    assert brynn.attacks_remaining == 0
    assert not any(action.kind == "attack" for action in state.available_actions())
    assert any(action.kind == "move" for action in state.available_actions())


def test_every_participant_uses_the_same_encounter_creature_state() -> None:
    session = load_scenario_directory(GOBLIN_SKIRMISH_DIR).create_session()
    session.read()

    assert session.encounter_state is not None
    assert len(session.encounter_state.creatures) == 6
    assert all(
        isinstance(creature_state, EncounterCreatureState)
        for creature_state in session.encounter_state.creatures.values()
    )
    assert session.encounter_state.creatures["player"].creature.name == "Aldren"
    assert session.encounter_state.creatures["champion_2"].creature.name == "Brynn"
    assert "player" not in session.__dict__


def test_secondary_champion_can_use_class_feature() -> None:
    session = load_scenario_directory(GOBLIN_SKIRMISH_DIR).create_session()
    session.read()
    assert session.encounter_state is not None
    brynn = session.encounter_state.creatures["champion_2"].creature
    brynn.current_health = 10
    session.choose(_action_id_by_label(session, "Wait"))

    second_wind = next(
        action
        for action in session.encounter_state.available_actions()
        if action.kind == "feature" and action.value == "second_wind"
    )
    result = _choose_advertised_action(session, second_wind)

    assert brynn.get_health() > 10
    assert session.encounter_state.current_decision().creature_ref == "champion_2"
    feature_event = next(
        event for event in result.events if event.type == "feature_used"
    )
    assert feature_event.creature_ref == "champion_2"
    assert feature_event.data["target_ref"] == "champion_2"


def test_any_user_controlled_creature_can_take_an_opportunity_attack() -> None:
    session = load_scenario_directory(GOBLIN_SKIRMISH_DIR).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    brynn = state.creatures["champion_2"]
    goblin = state.creatures["red_blade"]
    state.turn.index = 1
    brynn.position.x, brynn.position.y = 3, 3
    goblin.position.x, goblin.position.y = 3, 4

    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )
    _choose_advertised_action(session, move)

    assert state.current_decision().creature_ref == "red_blade"
    assert state.current_decision().kind == "reaction"
    opportunity_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "opportunity_attack"
    )
    _choose_advertised_action(session, opportunity_attack)

    assert goblin.reaction_available is False
    assert state.current_decision().creature_ref == "champion_2"
    assert (brynn.position.x, brynn.position.y) == (3, 2)


def test_user_controlled_goblin_chooses_reaction_to_primary_movement() -> None:
    session = load_scenario_directory(GOBLIN_SKIRMISH_DIR).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    aldren = state.creatures["player"]
    goblin = state.creatures["red_blade"]
    aldren.position.x, aldren.position.y = 3, 3
    goblin.position.x, goblin.position.y = 3, 4

    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )
    _choose_advertised_action(session, move)

    assert state.current_decision().creature_ref == "red_blade"
    opportunity_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "opportunity_attack"
    )
    _choose_advertised_action(session, opportunity_attack)

    assert goblin.reaction_available is False
    assert state.current_decision().creature_ref == "player"
    assert (aldren.position.x, aldren.position.y) == (3, 2)


def test_effectively_incapacitated_creature_gets_no_reaction_prompt() -> None:
    session = load_scenario_directory(GOBLIN_SKIRMISH_DIR).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    aldren = state.creatures["player"]
    goblin = state.creatures["red_blade"]
    aldren.position.x, aldren.position.y = 3, 3
    goblin.position.x, goblin.position.y = 3, 4
    state.conditions.append(
        build_applied_condition(
            condition=Condition.PARALYZED,
            source_ref="player",
            source_label=aldren.creature.name,
            target_ref="red_blade",
        )
    )

    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )
    _choose_advertised_action(session, move)

    assert state.current_decision().creature_ref == "player"
    assert state.current_decision().kind == "turn"
    assert (aldren.position.x, aldren.position.y) == (3, 2)
    assert goblin.reaction_available is True


def test_dragged_user_controlled_creature_does_not_get_opportunity_attack() -> None:
    session = load_scenario_directory(GOBLIN_SKIRMISH_DIR).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    aldren = state.creatures["player"]
    goblin = state.creatures["red_blade"]
    aldren.position.x, aldren.position.y = 3, 3
    goblin.position.x, goblin.position.y = 3, 4
    apply_grapple(
        state,
        condition_from_effect(
            EffectResult(
                kind="apply_condition",
                target_ref="red_blade",
                data={
                    "condition": "grappled",
                    "source_ref": "player",
                    "source_label": aldren.creature.name,
                },
            )
        ),
    )

    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )
    _choose_advertised_action(session, move)

    assert state.current_decision().creature_ref == "player"
    assert goblin.reaction_available is True
    assert (aldren.position.x, aldren.position.y) == (3, 2)
    assert (goblin.position.x, goblin.position.y) == (3, 3)


def test_ai_controlled_creature_resolves_opportunity_attack_automatically() -> None:
    session = load_scenario_directory(
        TACTICAL_SCENARIO_DIR,
        start_scene="goblin_encounter",
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    actor = state.creatures["player"]
    reactor = state.creatures["goblin_1"]
    actor.position.x, actor.position.y = 3, 3
    reactor.position.x, reactor.position.y = 3, 4
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)

    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )
    result = _choose_advertised_action(session, move)

    assert reactor.reaction_available is False
    assert state.current_decision().creature_ref == "player"
    assert any(
        event.type == "attack_resolved"
        and event.creature_ref == "goblin_1"
        and event.data["reaction"] is True
        for event in result.events
    )


def test_brynn_can_take_an_opportunity_attack() -> None:
    session = load_scenario_directory(GOBLIN_SKIRMISH_DIR).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    brynn = state.creatures["champion_2"]
    goblin = state.creatures["red_blade"]
    state.turn.index = 2
    goblin.position.x, goblin.position.y = 3, 3
    brynn.position.x, brynn.position.y = 3, 4
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)

    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "up"
    )
    _choose_advertised_action(session, move)

    assert state.current_decision().creature_ref == "champion_2"
    opportunity_attack = next(
        action
        for action in state.available_actions()
        if action.kind == "opportunity_attack"
    )
    _choose_advertised_action(session, opportunity_attack)

    assert brynn.reaction_available is False
    assert state.current_decision().creature_ref == "red_blade"
    assert (goblin.position.x, goblin.position.y) == (3, 2)


def test_team_members_are_not_valid_attack_targets() -> None:
    session = _all_external_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    heroes = next(team for team in state.definition.teams if team.id == "heroes")
    goblins = next(team for team in state.definition.teams if team.id == "goblins")
    heroes.members.append("goblin_1")
    goblins.members.remove("goblin_1")
    state.active_position.x = 2
    state.active_position.y = 2
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2

    player_actions = state.available_actions()

    assert not any(
        action.kind == "attack" and action.value == 0 for action in player_actions
    )


def test_externally_controlled_teammate_can_target_opposing_team() -> None:
    session = _all_external_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    heroes = next(team for team in state.definition.teams if team.id == "heroes")
    goblins = next(team for team in state.definition.teams if team.id == "goblins")
    heroes.members.append("goblin_1")
    goblins.members.remove("goblin_1")
    state.turn.index = 1
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2
    state.creatures["goblin_2"].position.x = 4
    state.creatures["goblin_2"].position.y = 2

    actions = state.available_actions()

    assert any(
        action.kind == "attack" and action.value == "goblin_2" for action in actions
    )
    assert not any(
        action.kind == "attack" and action.value == "player" for action in actions
    )


def test_paced_ai_resolves_one_visible_action_per_step() -> None:
    session = load_scenario_directory(
        TACTICAL_SCENARIO_DIR,
        start_scene="goblin_encounter",
    ).create_session()
    session.automatic_action_limit = 1
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state

    first = session.choose(_action_id_by_label(session, "Wait"))

    assert state.current_decision().creature_ref == "goblin_1"
    assert (
        len([event for event in first.events if event.type == "movement_resolved"]) == 1
    )
    assert state.requires_automatic_advance() is True

    second = session.advance_until_input_required()

    assert (
        len([event for event in second.events if event.type == "movement_resolved"])
        == 1
    )
    assert state.current_decision().creature_ref == "goblin_1"


def test_default_ai_still_resolves_until_the_next_user_decision() -> None:
    session = load_scenario_directory(
        TACTICAL_SCENARIO_DIR,
        start_scene="goblin_encounter",
    ).create_session()
    session.read()

    result = session.choose(_action_id_by_label(session, "Wait"))

    assert session.encounter_state is not None
    assert session.encounter_state.current_decision().creature_ref == "player"
    assert (
        len([event for event in result.events if event.type == "movement_resolved"]) > 1
    )
