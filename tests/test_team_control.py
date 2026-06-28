from pathlib import Path

from game.engine import Game
from game.save import create_save, restore_save

SAMPLE_GAME_DIR = Path(__file__).parents[1] / "sample_game"


def test_sample_encounter_loads_explicit_teams():
    game = Game(SAMPLE_GAME_DIR, start_scene="goblin_encounter")
    encounter = game.scenes["goblin_encounter"].encounter

    assert encounter is not None
    assert [(team.id, team.controller) for team in encounter.teams] == [
        ("heroes", "user"),
        ("goblins", "ai"),
    ]
    assert encounter.teams[1].members == ["goblin_1", "goblin_2", "goblin_3"]


def test_all_user_mode_pauses_for_each_goblin_turn():
    session = Game(
        SAMPLE_GAME_DIR,
        start_scene="goblin_encounter",
        control_mode="all-user",
    ).create_session()
    session.get_scene_view()
    state = session.encounter_state
    assert state is not None
    starting_position = (state.enemies[0].position.x, state.enemies[0].position.y)

    result = session.choose(session.get_scene_view().choices.index("Wait"))

    assert state.current_decision().actor_ref == "enemy:0"
    assert result.decision is not None
    assert result.decision["actor_ref"] == "enemy:0"
    assert (state.enemies[0].position.x, state.enemies[0].position.y) == starting_position
    actions = state.available_actions(session.player)
    assert actions
    assert {action.actor_ref for action in actions} == {"enemy:0"}
    assert "Wait" in [action.label for action in actions]
    assert any(action.kind == "move" for action in actions)


def test_user_controlled_goblin_can_move_then_end_turn():
    session = Game(
        SAMPLE_GAME_DIR,
        start_scene="goblin_encounter",
        control_mode="all-user",
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    session.choose(session.get_scene_view().choices.index("Wait"))
    start = (state.enemies[0].position.x, state.enemies[0].position.y)
    move = next(
        action
        for action in state.available_actions(session.player)
        if action.kind == "move"
    )

    session.choose(
        next(
            index
            for index, action in enumerate(session.get_scene_view().action_details)
            if action.id == move.id
        )
    )

    assert state.current_decision().actor_ref == "enemy:0"
    assert (state.enemies[0].position.x, state.enemies[0].position.y) != start
    assert state.enemies[0].movement_remaining == 5

    session.choose(session.get_scene_view().choices.index("Wait"))

    assert state.current_decision().actor_ref == "enemy:1"


def test_user_controlled_goblin_can_attack_opposing_player(monkeypatch):
    session = Game(
        SAMPLE_GAME_DIR,
        start_scene="goblin_encounter",
        control_mode="all-user",
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 2
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2
    monkeypatch.setattr("game.encounter.roll_die", lambda _sides: 20)
    monkeypatch.setattr("game.encounter.roll_dice", lambda _count, _sides: 1)
    session.choose(session.get_scene_view().choices.index("Wait"))

    attack = next(
        action
        for action in state.available_actions(session.player)
        if action.kind == "attack"
    )

    assert attack.actor_ref == "enemy:0"
    assert attack.value == "player"
    health_before = session.player.get_health()
    result = session.choose(
        next(
            index
            for index, action in enumerate(session.get_scene_view().action_details)
            if action.id == attack.id
        )
    )

    assert session.player.get_health() < health_before
    assert state.current_decision().actor_ref == "enemy:1"
    event = next(event for event in result.events if event.type == "attack_resolved")
    assert event.actor_ref == "enemy:0"
    assert event.data["target_ref"] == "player"


def test_team_members_are_not_valid_attack_targets():
    session = Game(
        SAMPLE_GAME_DIR,
        start_scene="goblin_encounter",
        control_mode="all-user",
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    heroes = next(team for team in state.definition.teams if team.id == "heroes")
    goblins = next(team for team in state.definition.teams if team.id == "goblins")
    heroes.members.append("goblin_1")
    goblins.members.remove("goblin_1")
    state.player_position.x = 2
    state.player_position.y = 2
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2

    player_actions = state.available_actions(session.player)

    assert not any(
        action.kind == "attack" and action.value == 0
        for action in player_actions
    )


def test_user_controlled_teammate_can_target_opposing_team():
    session = Game(
        SAMPLE_GAME_DIR,
        start_scene="goblin_encounter",
        control_mode="all-user",
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    heroes = next(team for team in state.definition.teams if team.id == "heroes")
    goblins = next(team for team in state.definition.teams if team.id == "goblins")
    heroes.members.append("goblin_1")
    goblins.members.remove("goblin_1")
    state.turn_index = 1
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2
    state.enemies[1].position.x = 4
    state.enemies[1].position.y = 2

    actions = state.available_actions(session.player)

    assert any(
        action.kind == "attack" and action.value == "enemy:1"
        for action in actions
    )
    assert not any(
        action.kind == "attack" and action.value == "player"
        for action in actions
    )


def test_all_user_mode_is_preserved_in_save_games():
    session = Game(
        SAMPLE_GAME_DIR,
        start_scene="goblin_encounter",
        control_mode="all-user",
    ).create_session()
    session.get_scene_view()

    save = create_save(session)
    restored = restore_save(save, SAMPLE_GAME_DIR)

    assert save.control_mode == "all-user"
    assert restored.control_mode == "all-user"
    assert restored.encounter_state is not None
    assert restored.encounter_state.control_mode == "all-user"
