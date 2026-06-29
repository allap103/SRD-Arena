from pathlib import Path

from game.encounter import EncounterAction
from game.engine import Game
from game.presentation import build_session_presentation
from game.save import load_from_file, save_to_file

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"


def _item_id_by_name(session, name: str) -> str:
    return next(item_id for item_id, item in session.item_templates.items() if item.name == name)


def test_goblin_encounter_scene_generates_runtime_actions_and_grid() -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    scene_view = session.get_scene_view()
    assert scene_view.scene_text is not None

    assert "P" in scene_view.scene_text
    assert "E" in scene_view.scene_text
    assert "Round 1 - Turn: Player" in scene_view.scene_text
    assert "Movement remaining: 6/6 squares" in scene_view.scene_text
    assert "Player HP:" in scene_view.scene_text
    assert "Move up" in scene_view.choices
    assert "Move up-right" in scene_view.choices
    assert "Wait" in scene_view.choices
    assert "Flee encounter" in scene_view.choices
    assert "Retreat until the encounter system is ready." not in scene_view.choices


def test_goblin_encounter_movement_consumes_movement_before_turn_advances() -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    scene_view = session.get_scene_view()
    move_up_index = scene_view.choices.index("Move up")
    result = session.choose(move_up_index)

    assert ("system", "You move up. Movement remaining: 5.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.player_position.x == 1
    assert session.encounter_state.player_position.y == 5
    assert session.encounter_state.player_movement_remaining == 5
    assert session.encounter_state.enemies[0].position.x == 5
    assert session.encounter_state.enemies[0].position.y == 2
    assert session.encounter_state.enemies[1].position.x == 6
    assert session.encounter_state.enemies[1].position.y == 2
    assert session.encounter_state.enemies[2].position.x == 4
    assert session.encounter_state.enemies[2].position.y == 1
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 1


def test_goblin_encounter_allows_diagonal_movement() -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    move_index = session.get_scene_view().choices.index("Move up-right")
    result = session.choose(move_index)

    assert ("system", "You move up-right. Movement remaining: 5.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.player_position.x == 2
    assert session.encounter_state.player_position.y == 5


def test_spending_last_movement_square_does_not_auto_end_turn() -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    for _ in range(6):
        scene_view = session.get_scene_view()
        move_right_index = scene_view.choices.index("Move right")
        result = session.choose(move_right_index)

    assert ("system", "You move right. Movement remaining: 0.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 1
    assert session.get_scene_view().choices.count("Wait") == 1


def test_goblin_encounter_wait_advances_enemy_turns() -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    move_up_index = session.get_scene_view().choices.index("Move up")
    session.choose(move_up_index)
    wait_index = session.get_scene_view().choices.index("Wait")
    result = session.choose(wait_index)

    assert ("system", "You hold your ground.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.enemies[0].position.x == 2
    assert session.encounter_state.enemies[0].position.y == 5
    assert session.encounter_state.enemies[1].position.x == 3
    assert session.encounter_state.enemies[1].position.y == 5
    assert session.encounter_state.enemies[2].position.x == 4
    assert session.encounter_state.enemies[2].position.y == 1
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 2


def test_advance_until_next_decision_runs_enemy_turns_until_player_turn() -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.turn_index = 1

    progress = session.encounter_state.advance_until_next_decision(session.player)

    assert progress.transition is None
    assert ("system", "Goblin moves down-left to (4, 3).") in progress.messages
    assert session.encounter_state.active_actor() == ("player", None)
    assert session.encounter_state.round_number == 2


def test_enemy_movement_can_pause_for_player_opportunity_attack(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 2
    session.encounter_state.player_position.y = 2
    session.encounter_state.enemies[0].position.x = 3
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.turn_index = 1

    def scripted_behavior():
        context = yield None
        while True:
            context = yield EncounterAction("Move", "move", "right")

    behavior = scripted_behavior()
    next(behavior)
    session.encounter_state._behaviors[0] = behavior

    progress = session.encounter_state.advance_until_next_decision(session.player)

    assert progress.paused_for_decision is True
    assert session.encounter_state.current_decision().kind == "reaction"
    labels = [action.label for action in session.encounter_state.available_actions(session.player)]
    assert labels == ["Opportunity attack Goblin", "Pass reaction"]

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 1)

    reaction = session.encounter_state.available_actions(session.player)[0]
    reaction_progress = session.encounter_state.apply_action(session.player, reaction)

    assert any(
        "Traveler hits Enemy 1 (Goblin)" in message
        for _, message in reaction_progress.messages
    )
    assert session.encounter_state.enemies[0].position.x > 3
    assert session.encounter_state.enemies[0].position.y == 2
    assert session.encounter_state.pending_action is None
    assert session.encounter_state.current_decision().actor_ref == "player"


def test_ranged_weapons_do_not_enable_opportunity_attacks() -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.player.equipment.equipped_items["right_hand"] = _item_id_by_name(session, "Longbow")
    session.encounter_state.player_position.x = 2
    session.encounter_state.player_position.y = 2
    session.encounter_state.enemies[0].position.x = 3
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[1].actor.current_health = 0
    session.encounter_state.enemies[2].actor.current_health = 0
    session.encounter_state.turn_index = 1

    def scripted_behavior():
        context = yield None
        while True:
            context = yield EncounterAction("Move", "move", "right")

    behavior = scripted_behavior()
    next(behavior)
    session.encounter_state._behaviors[0] = behavior

    progress = session.encounter_state.advance_until_next_decision(session.player)

    assert session.encounter_state.current_decision().kind == "turn"
    assert session.encounter_state.enemies[0].position.x > 3
    assert session.encounter_state.pending_action is None
    assert session.encounter_state.current_decision().actor_ref == "player"


def test_ranged_weapon_attacks_have_disadvantage_when_target_is_adjacent(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    enemy = session.encounter_state.enemies[0]
    enemy.behavior.type = "archer"
    enemy.actor.equipment.equipped_items["right_hand"] = _item_id_by_name(session, "Longbow")
    session.encounter_state._initialize_behaviors()
    enemy.position.x = 2
    enemy.position.y = 2
    session.encounter_state.enemies[1].actor.current_health = 0
    session.encounter_state.enemies[2].actor.current_health = 0
    session.encounter_state.player_position.x = 1
    session.encounter_state.player_position.y = 2
    session.encounter_state.turn_index = 1

    rolls = iter([17, 5, 4])
    monkeypatch.setattr("game.encounter.roll_die", lambda sides: next(rolls))
    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: next(rolls))

    progress = session.encounter_state.advance_until_next_decision(session.player)

    attack_event = next(
        event
        for event in progress.events
        if event.type == "attack_resolved" and event.actor_ref == "enemy:0"
    )
    assert attack_event.data["attack_roll_detail"]["attack_type"] == "ranged"
    assert attack_event.data["attack_roll_detail"]["mode"] == "disadvantage"
    assert attack_event.data["attack_roll_detail"]["dice"] == [17, 5]
    assert attack_event.data["attack_roll_detail"]["weapon_name"] == "Longbow"
    assert attack_event.data["hit"] is False


def test_archer_behavior_uses_ranged_weapon_without_closing_distance(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    enemy = session.encounter_state.enemies[0]
    enemy.behavior.type = "archer"
    session.encounter_state._initialize_behaviors()
    session.encounter_state.enemies[1].actor.current_health = 0
    session.encounter_state.enemies[2].actor.current_health = 0
    enemy.position.x = 5
    enemy.position.y = 2
    session.encounter_state.player_position.x = 1
    session.encounter_state.player_position.y = 6
    session.encounter_state.turn_index = 1

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 4)

    progress = session.encounter_state.advance_until_next_decision(session.player)

    attack_event = next(
        event
        for event in progress.events
        if event.type == "attack_resolved" and event.actor_ref == "enemy:0"
    )
    assert enemy.position.x == 5
    assert enemy.position.y == 2
    assert attack_event.data["attack_roll_detail"]["attack_type"] == "ranged"
    assert attack_event.data["attack_roll_detail"]["weapon_name"] == "Shortbow"


def test_weapon_runtime_model_tracks_attack_type() -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()

    longsword_id = _item_id_by_name(session, "Longsword")
    longbow_id = _item_id_by_name(session, "Longbow")
    shortbow_id = _item_id_by_name(session, "Shortbow")

    assert session.item_templates[longsword_id].weapon_stat is not None
    assert session.item_templates[longsword_id].weapon_stat.attack_type == "melee"
    assert session.item_templates[longbow_id].weapon_stat is not None
    assert session.item_templates[longbow_id].weapon_stat.attack_type == "ranged"
    assert session.item_templates[shortbow_id].weapon_stat is not None
    assert session.item_templates[shortbow_id].weapon_stat.range_normal == 80
    assert session.item_templates[shortbow_id].weapon_stat.range_long == 320


def test_goblin_encounter_allows_diagonal_attacks(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.player.combat_profile.attacks_per_attack_action = 1
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 5
    session.encounter_state.enemies[0].position.y = 2

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 4)

    scene_view = session.get_scene_view()
    attack_index = next(
        index
        for index, choice in enumerate(scene_view.choices)
        if choice.startswith("Attack enemy 1")
    )
    result = session.choose(attack_index)

    assert result.selected_choice_text is not None
    assert result.selected_choice_text.startswith("Attack enemy 1")
    assert any(
        "Traveler hits Enemy 1 (Goblin)" in message
        for _, message in result.messages
    )
    assert session.encounter_state is not None
    assert session.encounter_state.player_action_available is False
    assert session.encounter_state.player_attacks_remaining == 0
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.current_decision().actor_ref == "player"
    assert not any(
        choice.startswith("Attack enemy")
        for choice in session.get_scene_view().choices
    )
    attack_event = next(event for event in result.events if event.type == "attack_resolved")
    assert attack_event.data["attacker_label"] == "Traveler"
    assert attack_event.data["target_label"] == "Enemy 1 (Goblin)"
    assert attack_event.data["attack_roll"] == 25
    assert attack_event.data["attack_roll_detail"]["proficiency_bonus"] == 2
    assert attack_event.data["critical_hit"] is True
    assert attack_event.data["damage_roll_detail"]["dice"] == "2d8"
    assert attack_event.data["damage_roll_detail"]["weapon_name"] == "Longsword"


def test_natural_twenty_is_a_critical_hit_and_auto_hits(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.player.combat_profile.attacks_per_attack_action = 1
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].actor.attributes.base_armor_class = 30
    session.encounter_state.enemies[0].actor.current_health = 30
    damage_rolls = iter([4, 7])

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: next(damage_rolls))

    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    result = session.choose(attack_index)

    assert ("system", "Critical hit by Traveler!") in result.messages
    attack_event = next(event for event in result.events if event.type == "attack_resolved")
    assert attack_event.data["hit"] is True
    assert attack_event.data["critical_hit"] is True
    assert attack_event.data["attack_roll"] == 25
    assert attack_event.data["attack_roll_detail"]["critical_hit"] is True
    assert attack_event.data["damage"] == 14
    assert attack_event.data["damage_roll_detail"]["dice"] == "2d8"
    assert attack_event.data["damage_roll_detail"]["dice_values"] == [4, 7]
    assert attack_event.data["damage_roll_detail"]["modifier"] == 3
    assert attack_event.data["damage_roll_detail"]["critical_hit"] is True


def test_extra_attack_allows_second_attack_after_movement(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.player.combat_profile.attacks_per_attack_action = 2
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].actor.current_health = 20

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 1)

    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    first_result = session.choose(attack_index)

    attack_events = [event for event in first_result.events if event.type == "attack_resolved"]
    assert len(attack_events) == 1
    assert attack_events[0].data["attacks_remaining"] == 1
    assert session.encounter_state.enemies[0].actor.get_health() == 15
    assert session.encounter_state.player_action_available is False
    assert session.encounter_state.player_attacks_remaining == 1

    move_index = session.get_scene_view().choices.index("Move left")
    move_result = session.choose(move_index)

    assert ("system", "You move left. Movement remaining: 5.") in move_result.messages
    assert session.encounter_state.player_position.x == 3
    assert session.encounter_state.player_position.y == 3
    assert session.encounter_state.player_attacks_remaining == 1

    second_attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    second_result = session.choose(second_attack_index)

    second_attack_events = [event for event in second_result.events if event.type == "attack_resolved"]
    assert len(second_attack_events) == 1
    assert second_attack_events[0].data["attacks_remaining"] == 0
    assert session.encounter_state.enemies[0].actor.get_health() == 10
    assert session.encounter_state.player_attacks_remaining == 0
    assert not any(
        choice.startswith("Attack enemy")
        for choice in session.get_scene_view().choices
    )


def test_goblin_encounter_can_utilize_healing_potion(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.player.current_health = 10

    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 5)

    scene_view = session.get_scene_view()
    potion_index = scene_view.choices.index("Drink Potion of Healing")
    result = session.choose(potion_index)

    assert ("system", "Traveler drinks Potion of Healing.") in result.messages
    assert ("system", "Healing: 2d4=5 + 2 = 7; applied 7.") in result.messages
    assert ("system", "Potion of Healing is consumed.") in result.messages
    assert session.player.get_health() == 17
    assert not session.player.inventory.has_item("potion_of_healing")
    assert session.encounter_state is not None
    assert session.encounter_state.player_bonus_action_available is False
    assert session.encounter_state.turn_index == 0
    event = next(event for event in result.events if event.type == "item_used")
    assert event.data["kind"] == "utilize"
    assert event.data["mode"] == "drink"
    assert event.data["item_name"] == "Potion of Healing"
    assert event.data["consumed"] is True
    assert event.data["healing_roll_detail"]["dice"] == "2d4"
    assert event.data["healing_roll_detail"]["applied_healing"] == 7


def test_second_wind_appears_and_consumes_bonus_action(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.player.current_health = 10

    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 5)

    scene_view = session.get_scene_view()
    second_wind_index = scene_view.choices.index("Second Wind")
    result = session.choose(second_wind_index)

    assert ("system", "Traveler uses Second Wind.") in result.messages
    assert ("system", "Healing: 1d10=5 + level 2 = 7; applied 7.") in result.messages
    assert session.player.get_health() == 17
    assert session.encounter_state is not None
    assert session.encounter_state.player_bonus_action_available is False
    assert session.player.feature_uses_remaining["second_wind"] == 1
    assert "Second Wind" not in session.get_scene_view().choices
    event = next(event for event in result.events if event.type == "feature_used")
    assert event.data["feature_id"] == "second_wind"
    assert event.data["feature_name"] == "Second Wind"
    assert event.data["uses_remaining"] == 1
    assert event.data["healing_roll_detail"]["dice"] == "1d10"
    assert event.data["healing_roll_detail"]["applied_healing"] == 7


def test_second_wind_stays_visible_in_feature_column_when_unavailable(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.player.current_health = 10

    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 5)

    second_wind_index = session.get_scene_view().choices.index("Second Wind")
    session.choose(second_wind_index)

    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert "Second Wind" not in session.get_scene_view().choices
    assert [action.label for action in presentation.encounter.feature_actions] == ["Second Wind"]
    assert presentation.encounter.feature_actions[0].index == -1
    assert presentation.encounter.feature_actions[0].cost["bonus_action"] == 1


def test_goblin_encounter_attack_can_end_scene_with_victory(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.player.combat_profile.attacks_per_attack_action = 1
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].actor.current_health = 1
    session.encounter_state.enemies[1].actor.current_health = 0
    session.encounter_state.enemies[2].actor.current_health = 0

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.encounter.roll_dice", lambda num_dice, sides: 4)

    scene_view = session.get_scene_view()
    attack_index = next(
        index for index, choice in enumerate(scene_view.choices) if choice.startswith("Attack enemy 1")
    )
    result = session.choose(attack_index)

    assert result.selected_choice_text is not None
    assert result.selected_choice_text.startswith("Attack enemy 1")
    assert session.current_scene_id == "goblin_encounter_victory"
    assert result.scene_changed is True


def test_attack_consumes_action_until_next_turn(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.player.combat_profile.attacks_per_attack_action = 1
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 1)

    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    session.choose(attack_index)

    assert session.encounter_state.player_action_available is False
    assert not any(
        choice.startswith("Attack enemy")
        for choice in session.get_scene_view().choices
    )

    wait_index = session.get_scene_view().choices.index("Wait")
    session.choose(wait_index)

    assert session.encounter_state.player_action_available is True
    assert any(
        choice.startswith("Attack enemy")
        for choice in session.get_scene_view().choices
    )


def test_save_and_load_preserve_encounter_progress(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    move_up_index = session.get_scene_view().choices.index("Move up")
    session.choose(move_up_index)
    save_path = tmp_path / "encounter_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, FIXTURE_ENCOUNTER_DIR)

    assert loaded.encounter_state is not None
    assert loaded.current_scene_id == "goblin_encounter"
    assert loaded.encounter_state.player_position.x == 1
    assert loaded.encounter_state.player_position.y == 5
    assert loaded.encounter_state.enemies[0].position.x == 5
    assert loaded.encounter_state.enemies[0].position.y == 2
    assert loaded.encounter_state.turn_index == 0
    assert loaded.encounter_state.round_number == 1
    assert loaded.encounter_state.player_movement_remaining == 5
    assert loaded.encounter_state.player_action_available is True


def test_save_and_load_preserve_spent_action(tmp_path: Path, monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.player.combat_profile.attacks_per_attack_action = 1
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2

    monkeypatch.setattr("game.encounter.roll_die", lambda sides: 1)

    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    session.choose(attack_index)
    save_path = tmp_path / "spent_action_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, FIXTURE_ENCOUNTER_DIR)

    assert loaded.encounter_state is not None
    assert loaded.encounter_state.player_action_available is False
    assert not any(
        choice.startswith("Attack enemy")
        for choice in loaded.get_scene_view().choices
    )


def test_save_and_load_preserve_pending_reaction_state(tmp_path: Path) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 2
    session.encounter_state.player_position.y = 2
    session.encounter_state.enemies[0].position.x = 3
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.turn_index = 1

    def scripted_behavior():
        context = yield None
        while True:
            context = yield EncounterAction("Move", "move", "right")

    behavior = scripted_behavior()
    next(behavior)
    session.encounter_state._behaviors[0] = behavior
    session.encounter_state.advance_until_next_decision(session.player)
    save_path = tmp_path / "reaction_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, FIXTURE_ENCOUNTER_DIR)

    assert loaded.encounter_state is not None
    assert loaded.encounter_state.current_decision().kind == "reaction"
    assert loaded.encounter_state.pending_action is not None
    assert loaded.encounter_state.pending_action.actor_ref == "enemy:0"
