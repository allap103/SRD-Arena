from pathlib import Path

# mypy: disable-error-code="assignment,method-assign,return-value,index,arg-type"
from types import SimpleNamespace

import pytest

from srd_arena.domain.encounters.encounter import (
    ActionCost,
    EncounterAction,
    EncounterState,
)
from srd_arena.runtime.scenario import ScenarioLoader
from srd_arena.frontends.qt.app import CyoaPySide6Window
from srd_arena.domain.effects import EffectResult
from srd_arena.frontends.shared.session import (
    SpellSlotTrackView,
    build_session_presentation,
)
from srd_arena.frontends.shared.models import ActionView
from srd_arena.frontends.qt.ui.encounter import BattlefieldWidget
from srd_arena.frontends.qt.ui.encounter.config import TargetSelectionMode

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
TACTICAL_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "tactical_game"
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


def _action_index_by_prefix(session, prefix: str) -> int:
    return next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith(prefix)
    )


def _choose_directional_spell(session, label: str, aim_cell: tuple[int, int]):
    scene_view = session.get_scene_view()
    action = next(
        detail for detail in scene_view.action_details if detail.label == label
    )
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
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
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
    assert "Flee encounter" not in scene_view.choices
    assert "Retreat until the encounter system is ready." not in scene_view.choices


def test_initiative_is_rolled_for_all_combatants_at_encounter_start(
    monkeypatch,
) -> None:
    monkeypatch.setattr(EncounterState, "_roll_initiative", _ROLL_INITIATIVE)
    rolls = iter([12, 18, 7, 14])
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls)
    )
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"

    session.get_scene_view()

    assert session.encounter_state is not None
    assert [
        entry.actor_ref for entry in session.encounter_state.initiative_entries
    ] == [
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
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls)
    )
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"

    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert [
        creature.token_image
        for creature in presentation.encounter.battlefield.creatures
    ] == [
        "tokens/traveler.png",
        "tokens/goblin.png",
        "tokens/goblin.png",
        "tokens/goblin.png",
    ]
    assert [
        (entry.label, entry.total, entry.is_active)
        for entry in presentation.encounter.resources.initiative
    ] == [
        ("Enemy 1 (Goblin Warrior)", 20, True),
        ("Enemy 3 (Goblin Warrior)", 16, False),
        ("Player", 13, False),
        ("Enemy 2 (Goblin Warrior)", 9, False),
    ]


def test_goblin_encounter_movement_consumes_movement_before_turn_advances() -> None:
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"

    scene_view = session.get_scene_view()
    move_up_index = scene_view.choices.index("Move up")
    result = session.choose(move_up_index)

    assert ("system", "You move up. Movement remaining: 5.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.player_position.x == 1
    assert session.encounter_state.player_position.y == 5
    assert session.encounter_state.player_combatant.turn.movement_remaining == 5
    assert session.encounter_state.enemies[0].position.x == 5
    assert session.encounter_state.enemies[0].position.y == 2
    assert session.encounter_state.enemies[1].position.x == 6
    assert session.encounter_state.enemies[1].position.y == 2
    assert session.encounter_state.enemies[2].position.x == 4
    assert session.encounter_state.enemies[2].position.y == 1
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 1


def test_goblin_encounter_allows_diagonal_movement() -> None:
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"

    move_index = session.get_scene_view().choices.index("Move up-right")
    result = session.choose(move_index)

    assert ("system", "You move up-right. Movement remaining: 5.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.player_position.x == 2
    assert session.encounter_state.player_position.y == 5


def test_grappled_blocks_movement_and_disadvantages_attacks() -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
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
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3

    rolls = iter([20, 1])
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls)
    )

    scene_view = session.get_scene_view()
    grapple_index = next(
        index
        for index, choice in enumerate(scene_view.choices)
        if choice.startswith("Grapple enemy 1")
    )
    result = session.choose(grapple_index)

    assert ("system", "Traveler grapples Enemy 1 (Goblin Warrior).") in result.messages
    assert session.encounter_state.has_condition("enemy:0", "grappled") is True
    assert session.encounter_state.has_condition("player", "grappling") is True
    assert "Grapple enemy 1 (Goblin Warrior)" in scene_view.choices


def test_grappling_moves_target_and_costs_extra_movement() -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
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
    assert state.player_combatant.turn.movement_remaining == 4


def test_spending_last_movement_square_does_not_auto_end_turn() -> None:
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
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
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
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
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].creature.current_health = 30
    session.encounter_state.enemies[0].creature.current_health = 30

    assert "Cast Color Spray" in session.get_scene_view().choices


def test_burning_hands_appears_as_spell_action_when_enemy_is_in_range() -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2

    assert "Cast Burning Hands" in session.get_scene_view().choices


def test_presentation_derives_spell_slot_rows_from_player_spellcasting(
    monkeypatch,
) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )

    _choose_directional_spell(session, "Cast Color Spray", (4, 2))
    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert presentation.encounter.resources.spell_slots == (
        SpellSlotTrackView(level=1, remaining=3, maximum=4),
        SpellSlotTrackView(level=2, remaining=3, maximum=3),
        SpellSlotTrackView(level=3, remaining=2, maximum=2),
    )


def test_lesser_restoration_appears_when_player_has_removable_condition() -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
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


def test_color_spray_consumes_slot_and_applies_blinded_on_failed_save(
    monkeypatch,
) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.player.spellcasting is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 2))

    assert (
        "system",
        "Traveler casts Color Spray on Enemy 1 (Goblin Warrior).",
    ) in result.messages
    assert any(
        "is blinded until the end of your next turn" in message
        for _, message in result.messages
    )
    assert session.encounter_state.player_combatant.turn.actions_remaining == 0
    assert session.player.spellcasting.spell_slots_remaining[1] == 3
    assert session.encounter_state.has_condition("enemy:0", "blinded") is True
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Color Spray"
    assert spell_event.data["save_detail"]["ability"] == "constitution"
    assert spell_event.data["save_detail"]["success"] is False
    assert spell_event.data["effects"][0]["data"]["condition"] == "blinded"


def test_color_spray_cone_can_affect_multiple_enemies(monkeypatch) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
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
    state.enemies[2].creature.current_health = 0

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )

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
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 4
    state.enemies[0].position.x = 5
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 5
    state.enemies[1].position.y = 4
    state.enemies[2].creature.current_health = 0

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )

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
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 4
    state.enemies[1].position.y = 2
    state.enemies[2].creature.current_health = 0

    rolls = iter([5, 1, 2, 3, 16, 4, 5, 6])
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: next(rolls)
    )

    result = _choose_directional_spell(session, "Cast Burning Hands", (4, 3))

    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Burning Hands"
    assert spell_event.data["save_details"][0]["ability"] == "dexterity"
    assert spell_event.data["damage_roll_details"][0]["dice"] == "3d6"
    assert spell_event.data["damage_roll_details"][0]["applied_damage"] == 6
    assert spell_event.data["damage_roll_details"][1]["applied_damage"] == 7
    assert state.enemies[0].creature.get_health() == 4
    assert state.enemies[1].creature.get_health() == 3
    assert any("takes 6 fire damage." in message for _, message in result.messages)
    assert any(
        "takes 7 fire damage on a successful save." in message
        for _, message in result.messages
    )
    assert not any(
        "Enemy 2 (Goblin Warrior) is defeated." == message
        for _, message in result.messages
    )


def test_fireball_point_area_damages_multiple_enemies(monkeypatch) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
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
    starting_healths = [enemy.creature.get_health() for enemy in state.enemies]

    rolls = iter([1, 2, 3, 4, 5, 6, 1, 2, 5, 16, 3])
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls)
    )

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
    assert spell_event.data["damage_roll_details"][0]["applied_damage"] == min(
        24, starting_healths[0]
    )
    assert spell_event.data["damage_roll_details"][1]["final_damage"] == 12
    assert spell_event.data["damage_roll_details"][1]["applied_damage"] == min(
        12, starting_healths[1]
    )
    assert spell_event.data["damage_roll_details"][2]["final_damage"] == 24
    assert spell_event.data["damage_roll_details"][2]["applied_damage"] == min(
        24, starting_healths[2]
    )
    assert session.player.spellcasting.spell_slots_remaining[3] == 1
    assert state.enemies[0].creature.get_health() == 0
    assert state.enemies[1].creature.get_health() == 0
    assert state.enemies[2].creature.get_health() == 0


def test_pyside6_window_extracts_spell_area_overlay(monkeypatch) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 4
    state.enemies[1].position.y = 2
    state.enemies[2].creature.current_health = 0

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))
    area = next(
        event.data["area"] for event in result.events if event.type == "spell_cast"
    )

    assert area is not None
    assert area["shape"] == "cone"
    assert area["origin"] == {"x": 4, "y": 4}
    assert area["rasterization_policy"] == "coverage_threshold"
    assert area["coverage_threshold"] == 0.1
    assert len(area["cells"]) >= 2


def test_pyside6_window_does_not_keep_spell_overlay_after_cast(monkeypatch) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].creature.current_health = 0
    state.enemies[2].creature.current_health = 0

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )
    monkeypatch.setattr(
        "srd_arena.frontends.qt.app.QTimer",
        SimpleNamespace(singleShot=lambda _delay, callback: callback()),
    )

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))

    window = CyoaPySide6Window.__new__(CyoaPySide6Window)
    window.game = SimpleNamespace(encounter_state=session.encounter_state)
    window._presentation = SimpleNamespace(encounter=object())
    window._combat_log_scene_id = state.encounter_id
    window.dice_roll_panel = SimpleNamespace(
        append_entry=lambda _messages, _rolls: None,
    )
    window._scroll_roll_log_to_bottom = lambda: None
    window.refresh_view = lambda: None
    window.close = lambda: None

    CyoaPySide6Window._apply_turn_result(window, result)

    assert not hasattr(window, "_resolved_area_overlay")


def test_battlefield_widget_preview_overlay_reaims_directional_area(
    monkeypatch,
) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 4
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 3
    state.enemies[1].position.x = 4
    state.enemies[1].position.y = 2
    state.enemies[2].creature.current_health = 0

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))
    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    original_area = next(
        event.data["area"] for event in result.events if event.type == "spell_cast"
    )
    preview = BattlefieldWidget._preview_area_overlay(
        original_area,
        (6, 4),
        presentation.encounter.battlefield,
    )

    assert preview is not None
    assert preview["shape"] == "cone"
    assert preview["origin"] == {"x": 4, "y": 4}
    assert (
        preview["continuous_area"]["direction"]
        != original_area["continuous_area"]["direction"]
    )
    assert preview["cells"] != original_area["cells"]


def test_blinded_enemy_attacks_with_disadvantage(monkeypatch) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.player.spellcasting is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 2
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2
    state.enemies[1].creature.current_health = 0
    state.enemies[2].creature.current_health = 0
    rolls = iter([5, 17, 4, 1])
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: next(rolls, 3)
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 1
    )

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
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 2
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))

    attack_mode = state._attack_roll_mode_for(
        "player",
        "enemy:0",
        "melee",
        state.player_position,
        (state.enemies[0].position,),
    )

    assert attack_mode == "advantage"


def test_blinded_from_color_spray_expires_at_end_of_players_next_turn(
    monkeypatch,
) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 2
    state.player_position.y = 2
    state.enemies[0].position.x = 3
    state.enemies[0].position.y = 2
    state.enemies[1].creature.current_health = 0
    state.enemies[2].creature.current_health = 0
    rolls = iter([5, 3, 3])
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: next(rolls, 3)
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 1
    )

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))
    session.choose(session.get_scene_view().choices.index("Wait"))

    assert state.has_condition("enemy:0", "blinded") is True

    session.choose(session.get_scene_view().choices.index("Wait"))

    assert state.has_condition("enemy:0", "blinded") is False


def test_reapplying_blinded_refreshes_duration_without_duplication(monkeypatch) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 1
    state.player_position.y = 1
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 1
    state.enemies[1].creature.current_health = 0
    state.enemies[2].creature.current_health = 0
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 1
    )

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
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
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
    assert (
        state._attack_roll_mode_for(
            "player",
            "enemy:0",
            "melee",
            state.player_position,
            (state.enemies[0].position,),
        )
        == "advantage"
    )

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
    assert (
        state._attack_roll_mode_for(
            "player",
            "enemy:0",
            "melee",
            state.player_position,
            (state.enemies[0].position,),
        )
        == "normal"
    )


def test_lesser_restoration_consumes_bonus_action_and_removes_condition() -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
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

    assert (
        "system",
        "Traveler casts Lesser Restoration on Traveler.",
    ) in result.messages
    assert ("system", "Traveler is no longer blinded.") in result.messages
    assert state.has_condition("player", "blinded") is False
    assert state.player_combatant.turn.bonus_action_available is False
    assert state.player_combatant.turn.actions_remaining > 0
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


def test_advance_until_next_decision_runs_enemy_turns_until_player_turn() -> None:
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.turn_index = 1

    progress = session.encounter_state.advance_until_next_decision(session.player)

    assert progress.transition is None
    assert ("system", "Goblin Warrior moves down-left to (4, 3).") in progress.messages
    assert session.encounter_state.current_decision().actor_ref == "player"
    assert session.encounter_state.round_number == 2


def test_archer_behavior_uses_ranged_weapon_without_closing_distance(
    monkeypatch,
) -> None:
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    enemy = session.encounter_state.enemies[0]
    enemy.behavior.type = "archer"
    session.encounter_state._initialize_behaviors()
    session.encounter_state.enemies[1].creature.current_health = 0
    session.encounter_state.enemies[2].creature.current_health = 0
    enemy.position.x = 5
    enemy.position.y = 2
    session.encounter_state.player_position.x = 1
    session.encounter_state.player_position.y = 6
    session.encounter_state.turn_index = 1

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 20
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 4
    )

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


def test_natural_one_is_an_automatic_miss_for_attack_rolls(monkeypatch) -> None:
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].creature.attributes.base_armor_class = 0
    starting_health = session.encounter_state.enemies[0].creature.get_health()

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 1
    )

    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    result = session.choose(attack_index)

    assert ("system", "Traveler misses Enemy 1 (Goblin Warrior).") in result.messages
    attack_event = next(
        event for event in result.events if event.type == "attack_resolved"
    )
    assert attack_event.data["hit"] is False
    assert attack_event.data["critical_hit"] is False
    assert attack_event.data["damage"] == 0
    assert attack_event.data["damage_roll_detail"] is None
    assert attack_event.data["attack_roll_detail"]["critical_miss"] is True
    assert session.encounter_state.enemies[0].creature.get_health() == starting_health


def test_extra_attack_allows_second_attack_after_movement(monkeypatch) -> None:
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.player.combat_profile.attacks_per_attack_action = 2
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].creature.current_health = 20

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 20
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 1
    )

    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    first_result = session.choose(attack_index)

    attack_events = [
        event for event in first_result.events if event.type == "attack_resolved"
    ]
    assert len(attack_events) == 1
    assert attack_events[0].data["attacks_remaining"] == 1
    assert session.encounter_state.enemies[0].creature.get_health() == 15
    assert session.encounter_state.player_combatant.turn.actions_remaining == 0
    assert session.encounter_state.player_combatant.turn.attacks_remaining == 1

    move_index = session.get_scene_view().choices.index("Move left")
    move_result = session.choose(move_index)

    assert ("system", "You move left. Movement remaining: 5.") in move_result.messages
    assert session.encounter_state.player_position.x == 3
    assert session.encounter_state.player_position.y == 3
    assert session.encounter_state.player_combatant.turn.attacks_remaining == 1

    second_attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    second_result = session.choose(second_attack_index)

    second_attack_events = [
        event for event in second_result.events if event.type == "attack_resolved"
    ]
    assert len(second_attack_events) == 1
    assert second_attack_events[0].data["attacks_remaining"] == 0
    assert session.encounter_state.enemies[0].creature.get_health() == 10
    assert session.encounter_state.player_combatant.turn.attacks_remaining == 0
    assert not any(
        choice.startswith("Attack enemy") for choice in session.get_scene_view().choices
    )


def test_second_wind_appears_and_consumes_bonus_action(monkeypatch) -> None:
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"
    session.player.current_health = 10

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 5
    )

    scene_view = session.get_scene_view()
    second_wind_index = scene_view.choices.index("Second Wind")
    result = session.choose(second_wind_index)

    assert ("system", "Traveler uses Second Wind.") in result.messages
    assert ("system", "Healing: 1d10=5 + level 2 = 7; applied 7.") in result.messages
    assert session.player.get_health() == 17
    assert session.encounter_state is not None
    assert session.encounter_state.player_combatant.turn.bonus_action_available is False
    assert session.player.feature_uses_remaining["second_wind"] == 1
    assert "Second Wind" not in session.get_scene_view().choices
    event = next(event for event in result.events if event.type == "feature_used")
    assert event.data["feature_id"] == "second_wind"
    assert event.data["feature_name"] == "Second Wind"
    assert event.data["uses_remaining"] == 1
    assert event.data["healing_roll_detail"]["dice"] == "1d10"
    assert event.data["healing_roll_detail"]["applied_healing"] == 7


def test_second_wind_stays_visible_in_feature_column_when_unavailable(
    monkeypatch,
) -> None:
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"
    session.player.current_health = 10

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 5
    )

    second_wind_index = session.get_scene_view().choices.index("Second Wind")
    session.choose(second_wind_index)

    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert "Second Wind" not in session.get_scene_view().choices
    feature_actions = {
        action.label: action for action in presentation.encounter.feature_actions
    }
    assert set(feature_actions) == {"Second Wind", "Action Surge"}
    assert feature_actions["Second Wind"].index == -1
    assert feature_actions["Second Wind"].cost["bonus_action"] == 1


def test_action_surge_grants_additional_action_for_same_turn(monkeypatch) -> None:
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].creature.current_health = 30

    def fixed_roll(sides: int) -> int:
        return 18 if sides == 20 else 6

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", fixed_roll)
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 6
    )

    first_attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    session.choose(first_attack_index)

    assert session.encounter_state.player_combatant.turn.actions_remaining == 0

    scene_view = session.get_scene_view()
    action_surge_index = scene_view.choices.index("Action Surge")
    result = session.choose(action_surge_index)

    assert ("system", "Traveler uses Action Surge.") in result.messages
    assert session.encounter_state.player_combatant.turn.actions_remaining == 1
    assert session.encounter_state.player_combatant.turn.magic_actions_remaining == 0
    assert session.player.feature_uses_remaining["action_surge"] == 0
    updated_choices = session.get_scene_view().choices
    assert any(choice.startswith("Attack enemy ") for choice in updated_choices)
    assert not any(choice.startswith("Cast ") for choice in updated_choices)
    event = next(event for event in result.events if event.type == "feature_used")
    assert event.data["feature_id"] == "action_surge"
    assert event.data["granted_actions"] == 1


def test_presentation_surfaces_conditions_in_encounter_views(monkeypatch) -> None:
    session = (
        ScenarioLoader()
        .load(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.player_position.x = 4
    state.player_position.y = 3
    state.enemies[0].position.x = 4
    state.enemies[0].position.y = 2
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )

    _choose_directional_spell(session, "Cast Color Spray", (4, 2))
    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert "Blinded" in presentation.encounter.battlefield.summary_text
    assert presentation.encounter.resources.conditions == ()
    assert any(
        creature.actor_ref == "enemy:0" and creature.conditions == ("blinded",)
        for creature in presentation.encounter.battlefield.creatures
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
            label="Grapple enemy 1 (Goblin Warrior)",
            kind="grapple",
            actor_ref="player",
            value=0,
            cost={"action": 1},
        ),
    )

    assert bucket == "attack"


def test_directional_spell_target_mode_stays_available_without_creature_target_map() -> (
    None
):
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
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.player.combat_profile.attacks_per_attack_action = 1
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2
    session.encounter_state.enemies[0].creature.current_health = 1
    session.encounter_state.enemies[1].creature.current_health = 0
    session.encounter_state.enemies[2].creature.current_health = 0

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 20
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 4
    )

    scene_view = session.get_scene_view()
    attack_index = next(
        index
        for index, choice in enumerate(scene_view.choices)
        if choice.startswith("Attack enemy 1")
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
    session = ScenarioLoader().load(str(FIXTURE_ENCOUNTER_DIR)).create_session().start_encounter()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.player.combat_profile.attacks_per_attack_action = 1
    session.encounter_state.player_position.x = 4
    session.encounter_state.player_position.y = 3
    session.encounter_state.enemies[0].position.x = 4
    session.encounter_state.enemies[0].position.y = 2

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 1
    )

    attack_index = next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith("Attack enemy 1")
    )
    session.choose(attack_index)

    assert session.encounter_state.player_combatant.turn.actions_remaining == 0
    assert not any(
        choice.startswith("Attack enemy") for choice in session.get_scene_view().choices
    )

    wait_index = session.get_scene_view().choices.index("Wait")
    session.choose(wait_index)

    assert session.encounter_state.player_combatant.turn.actions_remaining > 0
    assert any(
        choice.startswith("Attack enemy") for choice in session.get_scene_view().choices
    )


def test_encounter_victory_waits_for_continue_before_restart() -> None:
    session = (
        ScenarioLoader()
        .load(str(FIXTURE_ENCOUNTER_DIR), start_scene="goblin_encounter")
        .create_session().start_encounter()
    )
    session.get_scene_view()
    assert session.encounter_state is not None
    for enemy in session.encounter_state.enemies:
        enemy.creature.current_health = 0

    wait_index = session.get_scene_view().choices.index("Wait")
    result = session.choose(wait_index)

    assert result.scene_changed is False
    assert session.current_scene_id == "goblin_encounter"
    assert session.pending_scene_transition is not None
    assert session.encounter_state is not None
    assert ("system", "Victory! Press continue to proceed.") in result.messages
    assert result.scene.scene_text == "Victory! Press continue to proceed."
    assert (
        session.pending_scene_transition.message
        == "Victory! Press continue to proceed."
    )
    assert result.scene.choices[0] == "Continue"

    continue_result = session.choose(0)

    assert continue_result.scene_changed is False
    assert session.pending_scene_transition is None
    assert session.current_scene_id == "goblin_encounter"
    assert session.encounter_state is not None
    assert all(
        enemy.creature.get_health() > 0 for enemy in session.encounter_state.enemies
    )
