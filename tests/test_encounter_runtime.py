from pathlib import Path
from types import SimpleNamespace

import pytest

from game.domain.combat.encounter import ActionCost, EncounterAction, EncounterState
from game.runtime.scenario import Game
from game.frontends.qt.app import CyoaPySide6Window
from game.domain.combat.features import EffectResult
from game.presentation.session import SpellSlotTrackView, build_session_presentation
from game.presentation.models import ActionView
from game.runtime.save import load_from_file, save_to_file
from game.frontends.qt.ui.encounter import BattlefieldWidget
from game.frontends.qt.ui.encounter.config import TargetSelectionMode

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
SAMPLE_GAME_DIR = Path(__file__).parents[1] / "app" / "content" / "scenarios" / "sample_game"
_ROLL_INITIATIVE = EncounterState._roll_initiative


@pytest.fixture(autouse=True)
def _player_first_initiative(monkeypatch):
    def _fixed_initiative(self, player):
        self.initiative_entries = []
        self.initiative_order = [
            "player",
            *(f"enemy:{index}" for index, _enemy in enumerate(self.enemies)),
        ]

    monkeypatch.setattr(EncounterState, "_roll_initiative", _fixed_initiative)


def _item_id_by_name(session, name: str) -> str:
    return next(item_id for item_id, item in session.item_templates.items() if item.name == name)


def _action_index_by_prefix(session, prefix: str) -> int:
    return next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith(prefix)
    )


def _choose_directional_spell(session, label: str, aim_cell: tuple[int, int]):
    scene_view = session.get_scene_view()
    action = next(detail for detail in scene_view.action_details if detail.label == label)
    return session.choose_encounter_action(
        EncounterAction(
            label=action.label,
            kind=action.kind,
            value=f"{action.value}@{aim_cell[0] + 0.5:.4f},{aim_cell[1] + 0.5:.4f}",
            id=action.id,
            actor_ref=action.actor_ref,
            cost=ActionCost(
                movement=action.cost.get("movement", 0),
                action=action.cost.get("action", 0),
                bonus_action=action.cost.get("bonus_action", 0),
                reaction=action.cost.get("reaction", 0),
            ),
            source_trigger_id=action.source_trigger_id,
        )
    )


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


def test_initiative_is_rolled_for_all_combatants_at_encounter_start(monkeypatch) -> None:
    monkeypatch.setattr(EncounterState, "_roll_initiative", _ROLL_INITIATIVE)
    rolls = iter([12, 18, 7, 14])
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda _sides: next(rolls))
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    session.get_scene_view()

    assert session.encounter_state is not None
    assert [entry.actor_ref for entry in session.encounter_state.initiative_entries] == [
        "enemy:0",
        "enemy:2",
        "player",
        "enemy:1",
    ]
    assert [entry.total for entry in session.encounter_state.initiative_entries] == [
        20,
        16,
        13,
        9,
    ]
    assert session.encounter_state.current_decision().actor_ref == "enemy:0"


def test_presentation_exposes_initiative_tracker(monkeypatch) -> None:
    monkeypatch.setattr(EncounterState, "_roll_initiative", _ROLL_INITIATIVE)
    rolls = iter([12, 18, 7, 14])
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda _sides: next(rolls))
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert [
        (entry.label, entry.total, entry.is_active)
        for entry in presentation.encounter.resources.initiative
    ] == [
        ("Enemy 1 (Goblin)", 20, True),
        ("Enemy 3 (Goblin)", 16, False),
        ("Player", 13, False),
        ("Enemy 2 (Goblin)", 9, False),
    ]


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


def test_grappled_blocks_movement_and_disadvantages_attacks() -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 6
    state.enemies[1].position.y = 2
    state.enemies[2].position.x = 1
    state.enemies[2].position.y = 1
    state._apply_effects(
        [
            EffectResult(
                kind="apply_status",
                target_ref="player",
                data={
                    "condition": "grappled",
                    "source_ref": "enemy:0",
                    "source_label": "Goblin",
                },
            ),
            EffectResult(
                kind="apply_status",
                target_ref="enemy:0",
                data={
                    "condition": "grappling",
                    "source_ref": "player",
                    "source_label": "Traveler",
                },
            ),
        ]
    )

    choices = session.get_scene_view().choices
    assert not any(choice.startswith("Move ") for choice in choices)
    assert (
        state._attack_roll_mode_for(
            session.player,
            "player",
            "enemy:1",
            "melee",
            state.player_position,
            tuple(enemy.position for enemy in state.enemies if enemy.is_alive),
        )
        == "disadvantage"
    )
    assert (
        state._attack_roll_mode_for(
            session.player,
            "player",
            "enemy:0",
            "melee",
            state.player_position,
            tuple(enemy.position for enemy in state.enemies if enemy.is_alive),
        )
        == "normal"
    )


def test_grapple_action_is_available_in_the_combat_menu(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3

    rolls = iter([20, 1])
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda _sides: next(rolls))

    scene_view = session.get_scene_view()
    grapple_index = next(index for index, choice in enumerate(scene_view.choices) if choice.startswith("Grapple enemy 1"))
    result = session.choose(grapple_index)

    assert ("system", "Traveler grapples Enemy 1 (Goblin).") in result.messages
    assert session.encounter_state.has_condition("enemy:0", "grappled") is True
    assert session.encounter_state.has_condition("player", "grappling") is True
    assert "Grapple enemy 1 (Goblin)" in scene_view.choices


def test_grapple_action_requires_a_free_hand_in_the_menu() -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    session.player.equipment.equipped_items["right_hand"] = _item_id_by_name(session, "Longsword")
    session.player.equipment.equipped_items["left_hand"] = _item_id_by_name(session, "Longbow")

    choices = session.get_scene_view().choices

    assert "Grapple enemy 1 (Goblin)" not in choices


def test_grapple_action_is_rejected_without_a_free_hand(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    session.player.equipment.equipped_items["right_hand"] = _item_id_by_name(session, "Longsword")
    session.player.equipment.equipped_items["left_hand"] = _item_id_by_name(session, "Longbow")
    starting_actions = state.player_actions_remaining

    rolls = iter([20, 1])
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda _sides: next(rolls))

    result = session.choose_encounter_action(
        EncounterAction(
            label="Grapple enemy 1 (Goblin)",
            kind="grapple",
            value=0,
            id="player-grapple-0",
            actor_ref="player",
            cost=ActionCost(action=1),
        )
    )

    assert ("system", "You need a free hand to grapple.") in result.messages
    assert state.has_condition("enemy:0", "grappled") is False
    assert state.has_condition("player", "grappling") is False
    assert state.player_actions_remaining == starting_actions


def test_grappling_moves_target_and_costs_extra_movement() -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 6
    state.enemies[1].position.y = 2
    state.enemies[2].position.x = 1
    state.enemies[2].position.y = 1
    state._apply_effects(
        [
            EffectResult(
                kind="apply_status",
                target_ref="player",
                data={
                    "condition": "grappling",
                    "source_ref": "enemy:0",
                    "source_label": "Goblin",
                },
            ),
            EffectResult(
                kind="apply_status",
                target_ref="enemy:0",
                data={
                    "condition": "grappled",
                    "source_ref": "player",
                    "source_label": "Traveler",
                },
            ),
        ]
    )

    move_up_index = session.get_scene_view().choices.index("Move up")
    result = session.choose(move_up_index)

    assert ("system", "You move up. Movement remaining: 4.") in result.messages
    assert state.player_position.x == 4
    assert state.player_position.y == 3
    assert state.enemies[0].position.x == 4
    assert state.enemies[0].position.y == 2
    assert state.player_movement_remaining == 4


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


def test_color_spray_appears_as_spell_action_when_enemy_is_in_range() -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].actor.current_health = 30
    session.encounter_state.enemies[0].actor.current_health = 30

    assert "Cast Color Spray" in session.get_scene_view().choices


def test_burning_hands_appears_as_spell_action_when_enemy_is_in_range() -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2

    assert "Cast Burning Hands" in session.get_scene_view().choices


def test_presentation_derives_spell_slot_rows_from_player_spellcasting(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)

    _choose_directional_spell(session, "Cast Color Spray", (4, 2))
    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert presentation.encounter.resources.spell_slots == (
        SpellSlotTrackView(level=1, remaining=3, maximum=4),
        SpellSlotTrackView(level=2, remaining=3, maximum=3),
        SpellSlotTrackView(level=3, remaining=2, maximum=2),
    )


def test_lesser_restoration_appears_when_player_has_removable_condition() -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.player.spellcasting is not None
    session.player.spellcasting.spell_slots_max[2] = 1
    session.player.spellcasting.spell_slots_remaining[2] = 1
    session.encounter_state._apply_effects(
        [
            EffectResult(
                kind="apply_status",
                target_ref="player",
                data={
                    "condition": "blinded",
                    "source_ref": "enemy:0",
                    "source_label": "Goblin",
                },
            )
        ]
    )

    assert "Cast Lesser Restoration" in session.get_scene_view().choices


def test_color_spray_consumes_slot_and_applies_blinded_on_failed_save(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.player.spellcasting is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 2))

    assert ("system", "Traveler casts Color Spray on Enemy 1 (Goblin).") in result.messages
    assert any("is blinded until the end of your next turn" in message for _, message in result.messages)
    assert session.encounter_state.player_action_available is False
    assert session.player.spellcasting.spell_slots_remaining[1] == 3
    assert session.encounter_state.has_condition("enemy:0", "blinded") is True
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Color Spray"
    assert spell_event.data["save_detail"]["ability"] == "constitution"
    assert spell_event.data["save_detail"]["success"] is False
    assert spell_event.data["effects"][0]["data"]["condition"] == "blinded"


def test_color_spray_cone_can_affect_multiple_enemies(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.player.spellcasting is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 4
    state.enemies[1].position.y = 2
    state.enemies[2].actor.current_health = 0

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))

    assert state.has_condition("enemy:0", "blinded") is True
    assert state.has_condition("enemy:1", "blinded") is True
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["target_refs"] == ["enemy:0", "enemy:1"]
    assert spell_event.data["area"]["shape"] == "cone"
    assert spell_event.data["area"]["origin"] == {"x": 4, "y": 4}
    assert spell_event.data["area"]["rasterization_policy"] == "coverage_threshold"
    assert spell_event.data["area"]["coverage_threshold"] == 0.1
    assert len(spell_event.data["save_details"]) == 2
    assert [effect["target_ref"] for effect in spell_event.data["effects"]] == [
        "enemy:0",
        "enemy:1",
    ]


def test_color_spray_cone_uses_continuous_aim_vector(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 4
    state.enemies[0].position.x = 5
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 5
    state.enemies[1].position.y = 4
    state.enemies[2].actor.current_health = 0

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (5, 3))

    assert state.has_condition("enemy:0", "blinded") is True
    assert state.has_condition("enemy:1", "blinded") is True
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["target_refs"] == ["enemy:0", "enemy:1"]
    assert spell_event.data["area"]["continuous_area"]["direction"] == {
        "x": 0.9486832980505138,
        "y": -0.31622776601683794,
    }


def test_burning_hands_cone_damages_multiple_enemies(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 4
    state.enemies[1].position.y = 2
    state.enemies[2].actor.current_health = 0

    rolls = iter([5, 1, 2, 3, 16, 4, 5, 6])
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: next(rolls))

    result = _choose_directional_spell(session, "Cast Burning Hands", (4, 3))

    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Burning Hands"
    assert spell_event.data["save_details"][0]["ability"] == "dexterity"
    assert spell_event.data["damage_roll_details"][0]["dice"] == "3d6"
    assert spell_event.data["damage_roll_details"][0]["applied_damage"] == 6
    assert spell_event.data["damage_roll_details"][1]["applied_damage"] == 7
    assert state.enemies[0].actor.get_health() == 1
    assert state.enemies[1].actor.get_health() == 0
    assert any("takes 6 fire damage." in message for _, message in result.messages)
    assert any("takes 7 fire damage on a successful save." in message for _, message in result.messages)
    assert any("Enemy 2 (Goblin) is defeated." == message for _, message in result.messages)


def test_fireball_point_area_damages_multiple_enemies(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.player.spellcasting is not None
    state = session.encounter_state
    state.player_position.x = 1
    state.player_position.y = 6
    state.enemies[0].position.x = 5
    state.enemies[0].position.y = 2
    state.enemies[1].position.x = 6
    state.enemies[1].position.y = 2
    state.enemies[2].position.x = 4
    state.enemies[2].position.y = 1
    starting_healths = [enemy.actor.get_health() for enemy in state.enemies]

    rolls = iter([1, 2, 3, 4, 5, 6, 1, 2, 5, 16, 3])
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda _sides: next(rolls))

    result = _choose_directional_spell(session, "Cast Fireball", (5, 2))

    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Fireball"
    assert spell_event.data["target_refs"] == ["enemy:0", "enemy:1", "enemy:2"]
    assert spell_event.data["area"]["shape"] == "radius"
    assert spell_event.data["area"]["origin"] == {"x": 5, "y": 2}
    assert spell_event.data["save_details"][0]["ability"] == "dexterity"
    assert spell_event.data["damage_roll_details"][0]["dice"] == "8d6"
    assert spell_event.data["damage_roll_details"][0]["dice_total"] == 24
    assert spell_event.data["damage_roll_details"][0]["final_damage"] == 24
    assert spell_event.data["damage_roll_details"][0]["applied_damage"] == min(24, starting_healths[0])
    assert spell_event.data["damage_roll_details"][1]["final_damage"] == 12
    assert spell_event.data["damage_roll_details"][1]["applied_damage"] == min(12, starting_healths[1])
    assert spell_event.data["damage_roll_details"][2]["final_damage"] == 24
    assert spell_event.data["damage_roll_details"][2]["applied_damage"] == min(24, starting_healths[2])
    assert session.player.spellcasting.spell_slots_remaining[3] == 1
    assert state.enemies[0].actor.get_health() == 0
    assert state.enemies[1].actor.get_health() == 0
    assert state.enemies[2].actor.get_health() == 0


def test_pyside6_window_extracts_spell_area_overlay(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 4
    state.enemies[1].position.y = 2
    state.enemies[2].actor.current_health = 0

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))
    area = next(
        event.data["area"]
        for event in result.events
        if event.type == "spell_cast"
    )

    assert area is not None
    assert area["shape"] == "cone"
    assert area["origin"] == {"x": 4, "y": 4}
    assert area["rasterization_policy"] == "coverage_threshold"
    assert area["coverage_threshold"] == 0.1
    assert len(area["cells"]) >= 2


def test_pyside6_window_does_not_keep_spell_overlay_after_cast(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].actor.current_health = 0
    state.enemies[2].actor.current_health = 0

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)
    monkeypatch.setattr(
        "game.frontends.qt.app.QTimer",
        SimpleNamespace(singleShot=lambda _delay, callback: callback()),
    )

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))

    window = CyoaPySide6Window.__new__(CyoaPySide6Window)
    window.session = session
    window._presentation = SimpleNamespace(encounter=object())
    window._combat_log_scene_id = state.scene_id
    window.dice_roll_panel = SimpleNamespace(
        append_entry=lambda _messages, _rolls: None,
    )
    window._scroll_roll_log_to_bottom = lambda: None
    window.refresh_view = lambda: None
    window.close = lambda: None

    CyoaPySide6Window._apply_turn_result(window, result)

    assert not hasattr(window, "_resolved_area_overlay")


def test_battlefield_widget_preview_overlay_reaims_directional_area(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 4
    state.enemies[1].position.y = 2
    state.enemies[2].actor.current_health = 0

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))
    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    original_area = next(
        event.data["area"]
        for event in result.events
        if event.type == "spell_cast"
    )
    preview = BattlefieldWidget._preview_area_overlay(
        original_area,
        (6, 4),
        presentation.encounter.battlefield,
    )

    assert preview is not None
    assert preview["shape"] == "cone"
    assert preview["origin"] == {"x": 4, "y": 4}
    assert preview["continuous_area"]["direction"] != original_area["continuous_area"]["direction"]
    assert preview["cells"] != original_area["cells"]


def test_blinded_enemy_attacks_with_disadvantage(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.player.spellcasting is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 2
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2
    state.enemies[1].actor.current_health = 0
    state.enemies[2].actor.current_health = 0
    rolls = iter([5, 17, 4, 1])
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: next(rolls, 3))
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 1)

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))
    result = session.choose(session.get_scene_view().choices.index("Wait"))

    attack_event = next(
        event
        for event in result.events
        if event.type == "attack_resolved" and event.actor_ref == "enemy:0"
    )
    assert attack_event.data["attack_roll_detail"]["mode"] == "disadvantage"
    assert attack_event.data["attack_roll_detail"]["dice"] == [17, 4]


def test_attacks_against_blinded_target_gain_advantage(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 2
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))

    attack_mode = state._attack_roll_mode_for(
        "player",
        "enemy:0",
        "melee",
        state.player_position,
        (state.enemies[0].position,),
    )

    assert attack_mode == "advantage"


def test_blinded_from_color_spray_expires_at_end_of_players_next_turn(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 2
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2
    state.enemies[1].actor.current_health = 0
    state.enemies[2].actor.current_health = 0
    rolls = iter([5, 3, 3])
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: next(rolls, 3))
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 1)

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))
    session.choose(session.get_scene_view().choices.index("Wait"))

    assert state.has_condition("enemy:0", "blinded") is True

    session.choose(session.get_scene_view().choices.index("Wait"))

    assert state.has_condition("enemy:0", "blinded") is False


def test_reapplying_blinded_refreshes_duration_without_duplication(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 1
    state.player_position.y = 1
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 1
    state.enemies[1].actor.current_health = 0
    state.enemies[2].actor.current_health = 0
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 1)

    _choose_directional_spell(session, "Cast Color Spray", (4, 1))
    session.choose(session.get_scene_view().choices.index("Wait"))
    _choose_directional_spell(session, "Cast Color Spray", (4, 1))

    assert state.has_condition("enemy:0", "blinded") is True
    assert len(state.conditions_for("enemy:0")) == 1

    session.choose(session.get_scene_view().choices.index("Wait"))
    assert state.has_condition("enemy:0", "blinded") is True

    session.choose(session.get_scene_view().choices.index("Wait"))
    assert state.has_condition("enemy:0", "blinded") is False


def test_remove_status_effect_clears_blinded_rules_immediately() -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 2
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2

    state._apply_effects(
        [
            EffectResult(
                kind="apply_status",
                target_ref="enemy:0",
                data={
                    "condition": "blinded",
                    "source_ref": "player",
                    "source_label": "Traveler",
                },
            )
        ]
    )
    assert state.has_condition("enemy:0", "blinded") is True
    assert state._attack_roll_mode_for(
        "player",
        "enemy:0",
        "melee",
        state.player_position,
        (state.enemies[0].position,),
    ) == "advantage"

    messages = state._apply_effects(
        [
            EffectResult(
                kind="message",
                target_ref="player",
                data={"channel": "system", "text": "Status removed."},
            ),
            EffectResult(
                kind="remove_status",
                target_ref="enemy:0",
                data={"condition": "blinded"},
            ),
        ]
    )

    assert messages == [("system", "Status removed.")]
    assert state.has_condition("enemy:0", "blinded") is False
    assert state._attack_roll_mode_for(
        "player",
        "enemy:0",
        "melee",
        state.player_position,
        (state.enemies[0].position,),
    ) == "normal"


def test_save_and_load_preserve_color_spray_condition_and_slots(tmp_path: Path, monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.player.spellcasting is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)

    _choose_directional_spell(session, "Cast Color Spray", (4, 2))
    save_path = tmp_path / "color_spray_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, SAMPLE_GAME_DIR)

    assert loaded.encounter_state is not None
    assert loaded.player.spellcasting is not None
    assert loaded.player.spellcasting.spell_slots_remaining[1] == 3
    assert loaded.encounter_state.has_condition("enemy:0", "blinded") is True


def test_lesser_restoration_consumes_bonus_action_and_removes_condition() -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.player.spellcasting is not None
    session.player.spellcasting.spell_slots_max[2] = 1
    session.player.spellcasting.spell_slots_remaining[2] = 1
    state = session.encounter_state
    state._apply_effects(
        [
            EffectResult(
                kind="apply_status",
                target_ref="player",
                data={
                    "condition": "blinded",
                    "source_ref": "enemy:0",
                    "source_label": "Goblin",
                },
            )
        ]
    )

    result = session.choose(_action_index_by_prefix(session, "Cast Lesser Restoration"))

    assert ("system", "Traveler casts Lesser Restoration on Traveler.") in result.messages
    assert ("system", "Traveler is no longer blinded.") in result.messages
    assert state.has_condition("player", "blinded") is False
    assert state.player_bonus_action_available is False
    assert state.player_action_available is True
    assert session.player.spellcasting.spell_slots_remaining[2] == 0
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Lesser Restoration"
    assert spell_event.data["target_ref"] == "player"
    assert spell_event.data["success"] is True
    assert spell_event.data["effects"][0]["kind"] == "remove_status"


def test_lesser_restoration_uses_magic_menu_bucket() -> None:
    bucket = CyoaPySide6Window._action_bucket_key(
        None,
        ActionView(
            index=0,
            id="player-spell-lesser-restoration-player",
            label="Cast Lesser Restoration",
            kind="spell",
            actor_ref="player",
            value="lesser_restoration:player",
            cost={"bonus_action": 1},
        ),
    )

    assert bucket == "magic"


def test_save_and_load_preserve_refreshed_blinded_duration(tmp_path: Path, monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 1
    state.player_position.y = 1
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 1
    state.enemies[1].actor.current_health = 0
    state.enemies[2].actor.current_health = 0
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 1)

    _choose_directional_spell(session, "Cast Color Spray", (4, 1))
    session.choose(session.get_scene_view().choices.index("Wait"))
    _choose_directional_spell(session, "Cast Color Spray", (4, 1))
    save_path = tmp_path / "refreshed_blind_save.json"

    save_to_file(session, save_path)
    loaded = load_from_file(save_path, SAMPLE_GAME_DIR)

    assert loaded.encounter_state is not None
    assert loaded.encounter_state.has_condition("enemy:0", "blinded") is True

    loaded.choose(loaded.get_scene_view().choices.index("Wait"))
    assert loaded.encounter_state.has_condition("enemy:0", "blinded") is True

    loaded.choose(loaded.get_scene_view().choices.index("Wait"))
    assert loaded.encounter_state.has_condition("enemy:0", "blinded") is False


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
        yield None
        while True:
            yield EncounterAction("Move", "move", "right")

    behavior = scripted_behavior()
    next(behavior)
    session.encounter_state._behaviors[0] = behavior

    progress = session.encounter_state.advance_until_next_decision(session.player)

    assert progress.paused_for_decision is True
    assert session.encounter_state.current_decision().kind == "reaction"
    labels = [action.label for action in session.encounter_state.available_actions(session.player)]
    assert labels == ["Opportunity attack Goblin", "Pass reaction"]

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 1)

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
        yield None
        while True:
            yield EncounterAction("Move", "move", "right")

    behavior = scripted_behavior()
    next(behavior)
    session.encounter_state._behaviors[0] = behavior

    session.encounter_state.advance_until_next_decision(session.player)

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
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: next(rolls))
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: next(rolls))

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

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 4)

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

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 4)

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

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: next(damage_rolls))

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


def test_natural_one_is_an_automatic_miss_for_attack_rolls(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].actor.attributes.base_armor_class = 0
    starting_health = session.encounter_state.enemies[0].actor.get_health()

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 1)

    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    result = session.choose(attack_index)

    assert ("system", "Traveler misses Enemy 1 (Goblin).") in result.messages
    attack_event = next(event for event in result.events if event.type == "attack_resolved")
    assert attack_event.data["hit"] is False
    assert attack_event.data["critical_hit"] is False
    assert attack_event.data["damage"] == 0
    assert attack_event.data["damage_roll_detail"] is None
    assert attack_event.data["attack_roll_detail"]["critical_miss"] is True
    assert session.encounter_state.enemies[0].actor.get_health() == starting_health


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

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 1)

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

    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 5)

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

    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 5)

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

    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 5)

    second_wind_index = session.get_scene_view().choices.index("Second Wind")
    session.choose(second_wind_index)

    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert "Second Wind" not in session.get_scene_view().choices
    feature_actions = {action.label: action for action in presentation.encounter.feature_actions}
    assert set(feature_actions) == {"Second Wind", "Action Surge"}
    assert feature_actions["Second Wind"].index == -1
    assert feature_actions["Second Wind"].cost["bonus_action"] == 1


def test_action_surge_grants_additional_action_for_same_turn(monkeypatch) -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].actor.current_health = 30

    def fixed_roll(sides: int) -> int:
        return 18 if sides == 20 else 6

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", fixed_roll)
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 6)

    first_attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    session.choose(first_attack_index)

    assert session.encounter_state.player_actions_remaining == 0

    scene_view = session.get_scene_view()
    action_surge_index = scene_view.choices.index("Action Surge")
    result = session.choose(action_surge_index)

    assert ("system", "Traveler uses Action Surge.") in result.messages
    assert session.encounter_state.player_actions_remaining == 1
    assert session.encounter_state.player_magic_actions_remaining == 0
    assert session.player.feature_uses_remaining["action_surge"] == 0
    updated_choices = session.get_scene_view().choices
    assert any(choice.startswith("Attack enemy ") for choice in updated_choices)
    assert not any(choice.startswith("Cast ") for choice in updated_choices)
    event = next(event for event in result.events if event.type == "feature_used")
    assert event.data["feature_id"] == "action_surge"
    assert event.data["granted_actions"] == 1


def test_presentation_surfaces_conditions_in_encounter_views(monkeypatch) -> None:
    session = Game(str(SAMPLE_GAME_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 3
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 2
    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 5)

    _choose_directional_spell(session, "Cast Color Spray", (4, 2))
    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert "Blinded" in presentation.encounter.battlefield.summary_text
    assert presentation.encounter.resources.conditions == ()
    assert any(
        actor.actor_ref == "enemy:0" and actor.conditions == ("blinded",)
        for actor in presentation.encounter.battlefield.actors
    )


def test_spell_actions_map_to_magic_menu_bucket() -> None:
    bucket = CyoaPySide6Window._action_bucket_key(
        None,
        ActionView(
            index=0,
            id="player-spell-color_spray",
            label="Cast Color Spray",
            kind="spell",
            actor_ref="player",
            value="color_spray",
            cost={"action": 1},
        ),
    )

    assert bucket == "magic"


def test_grapple_actions_map_to_attack_menu_bucket() -> None:
    bucket = CyoaPySide6Window._action_bucket_key(
        None,
        ActionView(
            index=0,
            id="player-grapple-0",
            label="Grapple enemy 1 (Goblin)",
            kind="grapple",
            actor_ref="player",
            value=0,
            cost={"action": 1},
        ),
    )

    assert bucket == "attack"


def test_directional_spell_target_mode_stays_available_without_actor_target_map() -> None:
    window = CyoaPySide6Window.__new__(CyoaPySide6Window)
    window._pending_target_mode = TargetSelectionMode(
        kind="spell",
        source_trigger_id="player-spell-color_spray",
    )
    actions = [
        ActionView(
            index=0,
            id="player-spell-color_spray",
            label="Cast Color Spray",
            kind="spell",
            actor_ref="player",
            value="color_spray",
            cost={"action": 1},
        )
    ]

    assert CyoaPySide6Window._target_mode_is_available(window, actions, {}) is True


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

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("game.domain.combat.encounter.roll_dice", lambda num_dice, sides: 4)

    scene_view = session.get_scene_view()
    attack_index = next(
        index for index, choice in enumerate(scene_view.choices) if choice.startswith("Attack enemy 1")
    )
    result = session.choose(attack_index)

    assert result.selected_choice_text is not None
    assert result.selected_choice_text.startswith("Attack enemy 1")
    assert session.current_scene_id == "goblin_encounter"
    assert session.pending_scene_transition is not None
    assert session.encounter_state is not None
    assert result.scene_changed is False
    assert result.scene.choices[0] == "Continue"


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

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 1)

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

    monkeypatch.setattr("game.domain.combat.encounter.roll_die", lambda sides: 1)

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
        yield None
        while True:
            yield EncounterAction("Move", "move", "right")

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


def test_encounter_victory_waits_for_continue_before_scene_transition() -> None:
    session = Game(str(FIXTURE_ENCOUNTER_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    for enemy in session.encounter_state.enemies:
        enemy.actor.current_health = 0

    wait_index = session.get_scene_view().choices.index("Wait")
    result = session.choose(wait_index)

    assert result.scene_changed is False
    assert session.current_scene_id == "goblin_encounter"
    assert session.pending_scene_transition is not None
    assert session.encounter_state is not None
    assert ("system", "The last goblin falls. You catch your breath before moving on.") in result.messages
    assert result.scene.scene_text == (
        "As you charge towards the goblins, they quickly ready their weapons and prepare "
        "to fight. The goblin with the bow takes aim at you, while the other two reach "
        "for their primitive swords. The battle begins!"
    )
    assert session.pending_scene_transition.message == (
        "The last goblin falls. You catch your breath before moving on."
    )
    assert result.scene.choices[0] == "Continue"

    continue_result = session.choose(0)

    assert continue_result.scene_changed is True
    assert session.pending_scene_transition is None
    assert session.current_scene_id == "goblin_encounter_victory"
