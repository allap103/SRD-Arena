"""Exercise immediate and persistent authored spell resolution."""

from dataclasses import replace
from types import SimpleNamespace
from typing import cast as type_cast

import pytest

from srd_arena.application.interactions import game_update
from srd_arena.application.observations import (
    ActionObservation,
    observe_session,
)
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.spells import (
    load_spell_catalog,
)
from srd_arena.domain.effects import EffectResult
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.modifiers import RollModifier
from srd_arena.domain.effects.rule_effects import (
    DamageReduction,
    DamageResistance,
    MaximumHitPointAdjustment,
    RollAdjustment,
)
from srd_arena.domain.effects.runtime import (
    EffectPolarity,
)
from srd_arena.domain.encounters.effect_lifecycle.repeat_saves import (
    resolve_end_turn_effects,
)
from srd_arena.domain.encounters.effect_lifecycle.turn_start import (
    expire_ongoing_effects_for_turn_start,
)
from srd_arena.domain.encounters.encounter import (
    EncounterAction,
)
from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
from srd_arena.domain.encounters.state_combat import attack_roll_mode_for
from srd_arena.domain.encounters.state_runtime import apply_encounter_effects
from srd_arena.domain.geometry import Position
from srd_arena.domain.spells.rules import (
    parse_spell_action_ability,
    parse_spell_action_damage_type,
    parse_spell_action_slot,
)
from srd_arena.frontends.gui.app import GameWindow
from srd_arena.frontends.gui.presentation.models import (
    SessionPresentation,
    SpellSlotTrackView,
)
from srd_arena.frontends.gui.presentation.session import build_session_presentation
from srd_arena.frontends.gui.ui.encounter.action_menus import action_bucket
from srd_arena.frontends.gui.ui.encounter.area_previews import preview_area_overlay
from srd_arena.frontends.gui.ui.sidebar import GameSidebar
from srd_arena.infrastructure.scenarios import load_scenario_directory
from tests.encounter_runtime_support import (
    ORCHESTRATOR as _ORCHESTRATOR,
)
from tests.encounter_runtime_support import (
    TACTICAL_SCENARIO_DIR,
    player_first_initiative,
)
from tests.encounter_runtime_support import (
    action_id_by_label as _action_id_by_label,
)
from tests.encounter_runtime_support import (
    action_id_by_prefix as _action_id_by_prefix,
)
from tests.encounter_runtime_support import (
    action_labels as _action_labels,
)
from tests.encounter_runtime_support import (
    active_creature as _active_creature,
)
from tests.encounter_runtime_support import (
    as_mapping as _mapping,
)
from tests.encounter_runtime_support import (
    as_sequence as _sequence,
)
from tests.encounter_runtime_support import (
    build_referenced_spell as _build_referenced_spell,
)
from tests.encounter_runtime_support import (
    choose_directional_spell as _choose_directional_spell,
)
from tests.encounter_runtime_support import (
    use_deterministic_dice as _use_deterministic_dice,
)

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)


def test_color_spray_appears_as_spell_action_when_enemy_is_in_range() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    session.encounter_state.creatures["goblin_1"].creature.current_health = 30
    session.encounter_state.creatures["goblin_1"].creature.current_health = 30

    assert "Cast Color Spray" in _action_labels(session)


def test_burning_hands_appears_as_spell_action_when_enemy_is_in_range() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2

    assert "Cast Burning Hands" in _action_labels(session)
    assert "Cast Burning Hands (Level 2)" in _action_labels(session)
    assert "Cast Burning Hands (Level 3)" in _action_labels(session)


def test_presentation_derives_spell_slot_rows_from_player_spellcasting() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    _use_deterministic_dice(session, die_roller=lambda sides: 5)

    _choose_directional_spell(session, "Cast Color Spray", (4, 2))
    presentation = build_session_presentation(observe_session(session))

    assert presentation.encounter is not None
    assert presentation.encounter.resources.spell_slots == (
        SpellSlotTrackView(level=1, remaining=3, maximum=4),
        SpellSlotTrackView(level=2, remaining=3, maximum=3),
        SpellSlotTrackView(level=3, remaining=2, maximum=2),
    )


def test_lesser_restoration_appears_when_player_has_removable_condition() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.spell_slots_max[2] = 1
    caster.spellcasting.spell_slots_remaining[2] = 1
    apply_encounter_effects(
        session.encounter_state,
        [
            EffectResult(
                kind="apply_condition",
                target_ref="player",
                data={
                    "condition": "blinded",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            )
        ],
    )

    assert any(
        label.startswith("Cast Lesser Restoration") for label in _action_labels(session)
    )


def test_color_spray_consumes_slot_and_applies_blinded_on_failed_save() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2

    _use_deterministic_dice(session, die_roller=lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 2))

    assert ("system", "Traveler casts Color Spray.") in result.messages
    assert any(
        message == "Color Spray affects Goblin Warrior."
        for _, message in result.messages
    )
    assert session.encounter_state.active_action_available is False
    assert caster.spellcasting.spell_slots_remaining[1] == 3
    assert session.encounter_state.has_condition("goblin_1", Condition.BLINDED) is True
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Color Spray"
    save_detail = _mapping(spell_event.data["save_detail"])
    assert save_detail["ability"] == "constitution"
    assert save_detail["success"] is False
    effects = _sequence(spell_event.data["effects"])
    effect_data = _mapping(_mapping(effects[0])["data"])
    assert effect_data["condition"] == "blinded"


def test_color_spray_cone_can_affect_multiple_enemies() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    assert _active_creature(session).spellcasting is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 4
    state.creatures["goblin_2"].position.y = 2
    state.creatures["goblin_3"].creature.current_health = 0

    _use_deterministic_dice(session, die_roller=lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))

    assert state.has_condition("goblin_1", Condition.BLINDED) is True
    assert state.has_condition("goblin_2", Condition.BLINDED) is True
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["target_refs"] == ["goblin_1", "goblin_2"]
    area = _mapping(spell_event.data["area"])
    assert area["shape"] == "cone"
    assert area["origin"] == {"x": 4, "y": 4}
    assert area["rasterization_policy"] == "coverage_threshold"
    assert area["coverage_threshold"] == 0.1
    assert len(_sequence(spell_event.data["save_details"])) == 2
    effects = _sequence(spell_event.data["effects"])
    assert [_mapping(effect)["target_ref"] for effect in effects] == [
        "goblin_1",
        "goblin_2",
    ]


def test_color_spray_cone_uses_continuous_aim_vector() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 5
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 5
    state.creatures["goblin_2"].position.y = 4
    state.creatures["goblin_3"].creature.current_health = 0

    _use_deterministic_dice(session, die_roller=lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (5, 3))

    assert state.has_condition("goblin_1", Condition.BLINDED) is True
    assert state.has_condition("goblin_2", Condition.BLINDED) is True
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["target_refs"] == ["goblin_1", "goblin_2"]
    area = _mapping(spell_event.data["area"])
    continuous_area = _mapping(area["continuous_area"])
    assert continuous_area["direction"] == {
        "x": 0.9486832980505138,
        "y": -0.31622776601683794,
    }


def test_burning_hands_cone_damages_multiple_enemies() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 4
    state.creatures["goblin_2"].position.y = 2
    state.creatures["goblin_3"].creature.current_health = 0

    rolls = iter([5, 1, 2, 3, 16, 4, 5, 6])
    _use_deterministic_dice(session, die_roller=lambda sides: next(rolls))

    result = _choose_directional_spell(session, "Cast Burning Hands", (4, 3))

    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Burning Hands"
    save_details = _sequence(spell_event.data["save_details"])
    assert _mapping(save_details[0])["ability"] == "dexterity"
    damage_roll_details = _sequence(spell_event.data["damage_roll_details"])
    first_damage = _mapping(damage_roll_details[0])
    second_damage = _mapping(damage_roll_details[1])
    assert first_damage["dice"] == "3d6"
    assert first_damage["applied_damage"] == 8
    assert second_damage["applied_damage"] == 4
    assert first_damage["dice_values"] == [5, 1, 2]
    assert second_damage["dice_values"] == [5, 1, 2]
    assert state.creatures["goblin_1"].creature.get_health() == 2
    assert state.creatures["goblin_2"].creature.get_health() == 6
    assert (
        sum("Burning Hands damages" in message for _, message in result.messages) == 2
    )
    assert not any(
        message == "Enemy 2 (Goblin Warrior) is defeated."
        for _, message in result.messages
    )


def test_burning_hands_can_use_and_scale_a_higher_level_slot() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)

    result = _choose_directional_spell(session, "Cast Burning Hands (Level 3)", (4, 3))

    event = next(event for event in result.events if event.type == "spell_cast")
    assert event.data["slot_level"] == 3
    damage_roll_detail = _mapping(event.data["damage_roll_detail"])
    assert damage_roll_detail["dice"] == "5d6"
    assert event.data["spell_slots_remaining"] == 1


def test_fireball_point_area_damages_multiple_enemies() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    state = session.encounter_state
    state.active_position.x = 1
    state.active_position.y = 6
    state.creatures["goblin_1"].position.x = 5
    state.creatures["goblin_1"].position.y = 2
    state.creatures["goblin_2"].position.x = 6
    state.creatures["goblin_2"].position.y = 2
    state.creatures["goblin_3"].position.x = 4
    state.creatures["goblin_3"].position.y = 1
    starting_healths = [
        creature_state.creature.get_health()
        for creature_ref, creature_state in state.creatures.items()
        if creature_ref != state.current_decision().creature_ref
    ]

    rolls = iter([1, 2, 3, 4, 5, 6, 1, 2, 5, 16, 3])
    _use_deterministic_dice(session, die_roller=lambda _sides: next(rolls))

    result = _choose_directional_spell(session, "Cast Fireball", (5, 2))

    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Fireball"
    assert spell_event.data["target_refs"] == ["goblin_1", "goblin_2", "goblin_3"]
    area = _mapping(spell_event.data["area"])
    assert area["shape"] == "radius"
    assert area["origin"] == {"x": 5, "y": 2}
    save_details = _sequence(spell_event.data["save_details"])
    assert _mapping(save_details[0])["ability"] == "dexterity"
    damage_roll_details = _sequence(spell_event.data["damage_roll_details"])
    first_damage = _mapping(damage_roll_details[0])
    second_damage = _mapping(damage_roll_details[1])
    third_damage = _mapping(damage_roll_details[2])
    assert first_damage["dice"] == "8d6"
    assert first_damage["dice_total"] == 24
    assert first_damage["final_damage"] == 24
    assert first_damage["applied_damage"] == min(24, starting_healths[0])
    assert second_damage["final_damage"] == 12
    assert second_damage["applied_damage"] == min(12, starting_healths[1])
    assert third_damage["final_damage"] == 24
    assert third_damage["applied_damage"] == min(24, starting_healths[2])
    assert caster.spellcasting.spell_slots_remaining[3] == 1
    assert state.creatures["goblin_1"].creature.get_health() == 0
    assert state.creatures["goblin_2"].creature.get_health() == 0
    assert state.creatures["goblin_3"].creature.get_health() == 0


def test_pyside6_window_extracts_spell_area_overlay() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 4
    state.creatures["goblin_2"].position.y = 2
    state.creatures["goblin_3"].creature.current_health = 0

    _use_deterministic_dice(session, die_roller=lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))
    area = _mapping(
        next(
            event.data["area"] for event in result.events if event.type == "spell_cast"
        )
    )

    assert area is not None
    assert area["shape"] == "cone"
    assert area["origin"] == {"x": 4, "y": 4}
    assert area["rasterization_policy"] == "coverage_threshold"
    assert area["coverage_threshold"] == 0.1
    assert len(_sequence(area["cells"])) >= 2


def test_pyside6_window_does_not_keep_spell_overlay_after_cast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0

    _use_deterministic_dice(session, die_roller=lambda sides: 5)
    monkeypatch.setattr(
        "srd_arena.frontends.gui.app.QTimer",
        SimpleNamespace(singleShot=lambda _delay, callback: callback()),
    )

    result = game_update(
        session,
        _choose_directional_spell(session, "Cast Color Spray", (4, 3)),
    )

    window = GameWindow.__new__(GameWindow)
    window._presentation = type_cast(
        SessionPresentation,
        SimpleNamespace(encounter=object()),
    )
    window._combat_log_scene_id = state.encounter_id
    window._logged_round_number = state.round.number
    window.sidebar = type_cast(
        GameSidebar,
        SimpleNamespace(append_combat_log=lambda _messages, _rolls: None),
    )
    monkeypatch.setattr(window, "_scroll_roll_log_to_bottom", lambda: None)
    monkeypatch.setattr(window, "refresh_view", lambda: None)
    monkeypatch.setattr(window, "close", lambda: True)

    GameWindow._apply_turn_result(window, result)

    assert not hasattr(window, "_resolved_area_overlay")


def test_battlefield_widget_preview_overlay_reaims_directional_area() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 4
    state.creatures["goblin_2"].position.y = 2
    state.creatures["goblin_3"].creature.current_health = 0

    _use_deterministic_dice(session, die_roller=lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))
    presentation = build_session_presentation(observe_session(session))

    assert presentation.encounter is not None
    original_area = _mapping(
        next(
            event.data["area"] for event in result.events if event.type == "spell_cast"
        )
    )
    preview = preview_area_overlay(
        original_area,
        (6, 4),
        presentation.encounter.battlefield,
    )

    assert preview is not None
    assert preview["shape"] == "cone"
    assert preview["origin"] == {"x": 4, "y": 4}
    assert (
        _mapping(preview["continuous_area"])["direction"]
        != _mapping(original_area["continuous_area"])["direction"]
    )
    assert preview["cells"] != original_area["cells"]


def test_blinded_enemy_attacks_with_disadvantage() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    assert _active_creature(session).spellcasting is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 2
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    rolls = iter([5, 17, 4, 1])
    _use_deterministic_dice(session, die_roller=lambda sides: next(rolls, 3))

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))
    result = session.choose(_action_id_by_label(session, "Wait"))

    attack_event = next(
        event
        for event in result.events
        if event.type == "attack_resolved" and event.creature_ref == "goblin_1"
    )
    attack_roll_detail = _mapping(attack_event.data["attack_roll_detail"])
    assert attack_roll_detail["mode"] == "disadvantage"
    assert attack_roll_detail["dice"] == [17, 4]


def test_attacks_against_blinded_target_gain_advantage() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 2
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2
    _use_deterministic_dice(session, die_roller=lambda sides: 5)

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))

    attack_mode = attack_roll_mode_for(
        state,
        "player",
        "goblin_1",
        "melee",
        state.active_position,
        (state.creatures["goblin_1"].position,),
    )

    assert attack_mode == "advantage"


def test_blinded_from_color_spray_expires_at_end_of_players_next_turn() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 2
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    rolls = iter([5, 3, 3])
    _use_deterministic_dice(session, die_roller=lambda sides: next(rolls, 3))

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))
    session.choose(_action_id_by_label(session, "Wait"))

    assert state.has_condition("goblin_1", Condition.BLINDED) is True

    session.choose(_action_id_by_label(session, "Wait"))

    assert state.has_condition("goblin_1", Condition.BLINDED) is False


def test_reapplying_blinded_preserves_independent_durations() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 1
    state.active_position.y = 1
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 1
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    _use_deterministic_dice(session, die_roller=lambda sides: 5)

    _choose_directional_spell(session, "Cast Color Spray", (4, 1))
    session.choose(_action_id_by_label(session, "Wait"))
    _choose_directional_spell(session, "Cast Color Spray", (4, 1))

    assert state.has_condition("goblin_1", Condition.BLINDED) is True
    assert len(state.conditions_for("goblin_1")) == 2

    session.choose(_action_id_by_label(session, "Wait"))
    assert state.has_condition("goblin_1", Condition.BLINDED) is True

    session.choose(_action_id_by_label(session, "Wait"))
    assert state.has_condition("goblin_1", Condition.BLINDED) is False


def test_remove_condition_effect_clears_blinded_rules_immediately() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 2
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2

    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="apply_condition",
                target_ref="goblin_1",
                data={
                    "condition": "blinded",
                    "source_ref": "player",
                    "source_label": "Traveler",
                },
            )
        ],
    )
    assert state.has_condition("goblin_1", Condition.BLINDED) is True
    assert (
        attack_roll_mode_for(
            state,
            "player",
            "goblin_1",
            "melee",
            state.active_position,
            (state.creatures["goblin_1"].position,),
        )
        == "advantage"
    )

    messages = apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="message",
                target_ref="player",
                data={"channel": "system", "text": "Status removed."},
            ),
            EffectResult(
                kind="remove_condition",
                target_ref="goblin_1",
                data={"condition": "blinded"},
            ),
        ],
    )

    assert messages == [("system", "Status removed.")]
    assert state.has_condition("goblin_1", Condition.BLINDED) is False
    assert (
        attack_roll_mode_for(
            state,
            "player",
            "goblin_1",
            "melee",
            state.active_position,
            (state.creatures["goblin_1"].position,),
        )
        == "normal"
    )


def test_lesser_restoration_consumes_bonus_action_and_removes_condition() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.spell_slots_max[2] = 1
    caster.spellcasting.spell_slots_remaining[2] = 1
    state = session.encounter_state
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="apply_condition",
                target_ref="player",
                data={
                    "condition": "blinded",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            )
        ],
    )

    result = session.choose(_action_id_by_prefix(session, "Cast Lesser Restoration"))

    assert (
        "system",
        "Traveler casts Lesser Restoration on Traveler.",
    ) in result.messages
    assert ("system", "Traveler is no longer blinded.") in result.messages
    assert state.has_condition("player", Condition.BLINDED) is False
    assert state.active_bonus_action_available is False
    assert state.active_action_available is True
    assert caster.spellcasting.spell_slots_remaining[2] == 0
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Lesser Restoration"
    assert spell_event.data["target_ref"] == "player"
    assert spell_event.data["success"] is True
    effects = _sequence(spell_event.data["effects"])
    assert _mapping(effects[0])["kind"] == "remove_condition"


def test_cure_wounds_heals_through_generic_spell_resolution() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Cure Wounds", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[1] = 1
    caster.current_health = caster.get_max_health() - 12
    _use_deterministic_dice(session, die_roller=lambda _sides: 4)

    result = session.choose(_action_id_by_prefix(session, "Cast Cure Wounds"))

    assert caster.get_health() == caster.get_max_health() - 3
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["success"] is True
    healing_roll_detail = _mapping(spell_event.data["healing_roll_detail"])
    assert healing_roll_detail["total"] == 9
    assert healing_roll_detail["applied"] == 9


def test_false_life_grants_scaled_temporary_hit_points() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "False Life", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    _use_deterministic_dice(session, die_roller=lambda _sides: 3)

    result = session.choose(_action_id_by_prefix(session, "Cast False Life (Level 2)"))

    assert caster.temporary_hit_points == 15
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    temporary_hit_point_detail = _mapping(
        spell_event.data["temporary_hit_point_detail"]
    )
    assert temporary_hit_point_detail["total"] == 15
    assert temporary_hit_point_detail["applied"] == 15


def test_mass_healing_word_uses_one_roll_for_selected_targets() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Mass Healing Word", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[3] = 1
    for offset, target_ref in enumerate(("goblin_1", "goblin_2"), start=1):
        target = state.creatures[target_ref]
        target.position = Position(
            state.active_position.x + offset,
            state.active_position.y,
        )
        target.creature.current_health = target.creature.get_max_health() - 8
    _use_deterministic_dice(session, die_roller=lambda _sides: 3)

    initial = next(
        action
        for action in state.available_actions()
        if action.kind == "spell" and str(action.value) == "mass_healing_word:goblin_1"
    )
    _ORCHESTRATOR.submit(state, initial)
    add_second = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target" and action.value == "goblin_2"
    )
    _ORCHESTRATOR.submit(state, add_second)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )

    result = _ORCHESTRATOR.submit(state, confirm)

    event = next(event for event in result.events if event.type == "spell_cast")
    details = [
        _mapping(detail) for detail in _sequence(event.data["healing_roll_details"])
    ]
    assert [detail["target_ref"] for detail in details] == ["goblin_1", "goblin_2"]
    assert details[0]["dice_values"] == details[1]["dice_values"] == [3, 3]
    assert all(detail["applied"] == 7 for detail in details)


def test_heal_upcasts_and_removes_every_listed_condition() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell("Heal", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[7] = 1
    caster.max_health_override = 200
    caster.current_health = 50
    for condition in ("blinded", "poisoned"):
        apply_encounter_effects(
            state,
            [
                EffectResult(
                    kind="apply_condition",
                    target_ref="player",
                    data={
                        "condition": condition,
                        "source_ref": "goblin_1",
                        "source_label": "Goblin",
                    },
                )
            ],
        )

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("heal:player")
        and parse_spell_action_slot(str(action.value)) == 7
    )
    result = _ORCHESTRATOR.submit(state, action)

    assert caster.get_health() == 130
    assert state.has_condition("player", Condition.BLINDED) is False
    assert state.has_condition("player", Condition.POISONED) is False
    event = next(event for event in result.events if event.type == "spell_cast")
    healing_roll_detail = _mapping(event.data["healing_roll_detail"])
    assert healing_roll_detail["total"] == 80
    effects = [_mapping(effect) for effect in _sequence(event.data["effects"])]
    assert [_mapping(effect["data"])["condition"] for effect in effects] == [
        "blinded",
        "poisoned",
    ]


def test_protection_from_energy_offers_and_applies_one_resistance() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Protection from Energy", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[3] = 1

    actions = [
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("protection_from_energy:player")
    ]

    assert {
        parse_spell_action_damage_type(str(action.value)) for action in actions
    } == {"acid", "cold", "fire", "lightning", "thunder"}
    fire_action = next(
        action
        for action in actions
        if parse_spell_action_damage_type(str(action.value)) == "fire"
    )
    _ORCHESTRATOR.submit(state, fire_action)

    resistances = state.combat_rules.damage_resistances(state, "player").values
    assert "fire" in resistances
    assert "cold" not in resistances
    assert state.ongoing_effects[0].polarity is EffectPolarity.BENEFICIAL
    assert any(
        isinstance(rule, DamageResistance) and rule.damage_types == frozenset({"fire"})
        for rule in state.ongoing_effects[0].rule_effects
    )


def test_invisibility_is_classified_and_exported_as_beneficial() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Invisibility", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 1

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("invisibility:player")
    )
    _ORCHESTRATOR.submit(state, action)

    assert state.has_condition("player", Condition.INVISIBLE)
    effect = state.ongoing_effects[0]
    assert effect.polarity is EffectPolarity.BENEFICIAL


def test_enhance_ability_offers_and_applies_one_ability_choice() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Enhance Ability", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 1

    actions = [
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("enhance_ability:player")
    ]

    assert {parse_spell_action_ability(str(action.value)) for action in actions} == {
        "strength",
        "dexterity",
        "intelligence",
        "wisdom",
        "charisma",
    }
    strength_action = next(
        action
        for action in actions
        if parse_spell_action_ability(str(action.value)) == "strength"
    )
    _ORCHESTRATOR.submit(state, strength_action)

    assert (
        state.combat_rules.roll_modifiers(
            state,
            "player",
            "ability_check",
            ability="strength",
        ).mode
        == "advantage"
    )
    assert (
        state.combat_rules.roll_modifiers(
            state,
            "player",
            "ability_check",
            ability="dexterity",
        ).mode
        == "normal"
    )
    assert state.ongoing_effects[0].rule_effects == (
        RollAdjustment(
            RollModifier(
                "ability_check",
                "advantage",
                ability="strength",
            )
        ),
    )


def test_faerie_fire_applies_attack_advantage_only_after_failed_save() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Faerie Fire", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[1] = 1
    state.creatures["goblin_1"].position = Position(3, 3)
    state.creatures["goblin_2"].position = Position(4, 3)
    rolls = iter((1, 20))
    _use_deterministic_dice(session, die_roller=lambda _sides: next(rolls))

    result = _choose_directional_spell(session, "Cast Faerie Fire", (3, 3))

    assert result.events
    assert state.ongoing_effects[0].polarity is EffectPolarity.HARMFUL
    assert (
        state.combat_rules.roll_modifiers(
            state,
            "goblin_1",
            "attack_roll",
            subject="attacks_against_target",
            opposing_ref="player",
        ).mode
        == "advantage"
    )
    assert (
        state.combat_rules.roll_modifiers(
            state,
            "goblin_2",
            "attack_roll",
            subject="attacks_against_target",
            opposing_ref="player",
        ).mode
        == "normal"
    )


def test_phantasmal_killer_scales_and_repeats_typed_damage() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    target = state.creatures["goblin_1"].creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Phantasmal Killer", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_max[5] = 1
    caster.spellcasting.spell_slots_remaining[5] = 1
    target.current_health = 20
    target.statistics = replace(
        target.statistics,
        damage_resistances=frozenset({"psychic"}),
    )
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)
    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("phantasmal_killer:goblin_1")
        and parse_spell_action_slot(str(action.value)) == 5
    )

    _ORCHESTRATOR.submit(state, action)

    assert target.get_health() == 18
    assert (
        state.combat_rules.roll_modifiers(
            state,
            "goblin_1",
            "ability_check",
        ).mode
        == "disadvantage"
    )
    assert (
        state.combat_rules.roll_modifiers(
            state,
            "goblin_1",
            "attack_roll",
        ).mode
        == "disadvantage"
    )
    repeat_save = state.ongoing_effects[0].lifecycle.repeat_save
    assert repeat_save is not None
    assert [
        (damage.dice, damage.damage_type) for damage in repeat_save.failure_damage
    ] == [("5d10", "psychic")]

    progress = EncounterProgress()
    resolve_end_turn_effects(state, "goblin_1", progress)

    assert target.get_health() == 16
    assert state.ongoing_effects
    event = next(
        event for event in progress.events if event.type == "ongoing_effect_resolved"
    )
    assert event.data["spell_name"] == "Phantasmal Killer"
    assert _mapping(event.data["save_detail"])["success"] is False
    damage_roll_details = _sequence(event.data["damage_roll_details"])
    damage_roll_detail = _mapping(damage_roll_details[0])
    assert damage_roll_detail["dice"] == "5d10"
    assert damage_roll_detail["damage_type"] == "psychic"


def test_resistance_offers_and_applies_one_damage_reduction_type() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Resistance", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )

    actions = [
        action
        for action in state.available_actions()
        if action.kind == "spell" and str(action.value).startswith("resistance:player")
    ]
    assert len(actions) == 11
    fire_action = next(
        action
        for action in actions
        if parse_spell_action_damage_type(str(action.value)) == "fire"
    )

    _ORCHESTRATOR.submit(state, fire_action)

    reductions = [
        rule
        for effect in state.ongoing_effects
        for rule in effect.rule_effects
        if isinstance(rule, DamageReduction)
    ]
    assert [entry.damage_type for entry in reductions] == ["fire"]


def test_aid_upcasts_for_multiple_targets_and_reverts_on_expiry() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell("Aid", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[3] = 1
    target = state.creatures["goblin_1"]
    target.position = Position(state.active_position.x + 1, state.active_position.y)
    original = {
        "player": (
            state.combat_rules.effective_maximum_health(state, "player").value,
            caster.get_health(),
        ),
        "goblin_1": (
            state.combat_rules.effective_maximum_health(state, "goblin_1").value,
            target.creature.get_health(),
        ),
    }

    initial = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("aid:player")
        and parse_spell_action_slot(str(action.value)) == 3
    )
    _ORCHESTRATOR.submit(state, initial)
    add_target = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target" and action.value == "goblin_1"
    )
    _ORCHESTRATOR.submit(state, add_target)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    _ORCHESTRATOR.submit(state, confirm)

    assert (
        state.combat_rules.effective_maximum_health(state, "player").value
        == original["player"][0] + 10
    )
    assert caster.get_health() == original["player"][1] + 10
    assert (
        state.combat_rules.effective_maximum_health(state, "goblin_1").value
        == original["goblin_1"][0] + 10
    )
    assert target.creature.get_health() == original["goblin_1"][1] + 10

    state.round.number = 4801
    expire_ongoing_effects_for_turn_start(state, "player")

    assert (
        state.combat_rules.effective_maximum_health(state, "player").value,
        caster.get_health(),
    ) == original["player"]
    assert (
        state.combat_rules.effective_maximum_health(state, "goblin_1").value,
        target.creature.get_health(),
    ) == original["goblin_1"]


def test_mass_heal_uses_bounded_numeric_allocations() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Mass Heal", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[9] = 1
    target = state.creatures["goblin_1"]
    target.position = Position(state.active_position.x + 1, state.active_position.y)
    caster.max_health_override = 500
    caster.current_health = 100
    target.creature.max_health_override = 500
    target.creature.current_health = 100
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="apply_condition",
                target_ref="goblin_1",
                data={
                    "condition": "blinded",
                    "source_ref": "player",
                    "source_label": "Traveler",
                },
            )
        ],
    )

    initial = next(
        action
        for action in state.available_actions()
        if action.kind == "spell" and str(action.value).startswith("mass_heal:")
    )
    opened = _ORCHESTRATOR.submit(state, initial)

    assert opened.paused_for_decision
    assert state.interrupts.pending_spell_cast is not None
    assert state.interrupts.pending_spell_cast.resource_pool_total == 700
    for target_ref, amount in (("player", 300), ("goblin_1", 400)):
        _ORCHESTRATOR.submit(
            state,
            EncounterAction(
                label="Set healing allocation",
                kind="set_spell_resource_allocation",
                value=f"{target_ref}~{amount}",
                id=f"player-spell-allocation-{target_ref}",
                creature_ref="player",
            ),
        )
    rejected = _ORCHESTRATOR.submit(
        state,
        EncounterAction(
            label="Over-allocate healing",
            kind="set_spell_resource_allocation",
            value="player~301",
            id="player-spell-allocation-player",
            creature_ref="player",
        ),
    )
    assert rejected.events[-1].data["success"] is False
    assert rejected.events[-1].data["reason_code"] == "resource_pool_exceeded"
    assert "remaining healing pool" in rejected.messages[-1][1]
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    result = _ORCHESTRATOR.submit(state, confirm)

    assert caster.get_health() == 400
    assert target.creature.get_health() == 500
    assert state.has_condition("goblin_1", Condition.BLINDED) is False
    event = next(event for event in result.events if event.type == "spell_cast")
    healing_roll_details = [
        _mapping(detail) for detail in _sequence(event.data["healing_roll_details"])
    ]
    assert {
        detail["target_ref"]: detail["allocated"] for detail in healing_roll_details
    } == {"player": 300, "goblin_1": 400}


def test_greater_restoration_selects_a_specific_sourced_effect() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Greater Restoration", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[5] = 1
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="apply_condition",
                target_ref="player",
                data={
                    "condition": "charmed",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            )
        ],
        origin_id="charm-origin",
    )
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="player",
                data={
                    "effect_kind": "curse",
                    "source_ref": "goblin_2",
                    "source_label": "Goblin Hex",
                    "definition_id": "goblin_hex",
                    "target_refs": ["player"],
                },
            ),
        ],
        origin_id="curse-origin",
    )

    curse_action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("greater_restoration:player")
        and "curse@" in str(action.value)
    )
    result = _ORCHESTRATOR.submit(state, curse_action)

    assert state.has_condition("player", Condition.CHARMED)
    assert not any(effect.kind.value == "curse" for effect in state.ongoing_effects)
    event = next(event for event in result.events if event.type == "spell_cast")
    assert event.data["effects"] == [
        {
            "kind": "remove_ongoing_effects",
            "target_ref": "player",
            "success": True,
            "data": {
                "effect_kind": "curse",
                "effect_id": "ongoing:curse:curse-origin",
                "all": False,
            },
        }
    ]


def test_remove_curse_ends_every_curse_on_one_creature() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Remove Curse", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[3] = 1
    for index in (1, 2):
        apply_encounter_effects(
            state,
            [
                EffectResult(
                    kind="start_ongoing_effect",
                    target_ref="player",
                    data={
                        "effect_kind": "curse",
                        "source_ref": f"goblin_{index}",
                        "source_label": f"Curse {index}",
                        "definition_id": f"curse_{index}",
                        "target_refs": ["player"],
                    },
                )
            ],
            origin_id=f"curse-{index}",
        )

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell" and str(action.value) == "remove_curse:player"
    )
    _ORCHESTRATOR.submit(state, action)

    assert not any(effect.kind.value == "curse" for effect in state.ongoing_effects)


def test_greater_restoration_removes_all_maximum_hit_point_reductions() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Greater Restoration", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[5] = 1
    original = (
        state.combat_rules.effective_maximum_health(state, "player").value,
        caster.get_health(),
    )
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="player",
                data={
                    "effect_kind": "spell",
                    "source_ref": "goblin_1",
                    "source_label": "Withering Effect",
                    "definition_id": "withering_effect",
                    "target_refs": ["player"],
                },
                rule_effects=(MaximumHitPointAdjustment(-10, True),),
            )
        ],
        origin_id="withering-origin",
    )
    assert (
        state.combat_rules.effective_maximum_health(state, "player").value,
        caster.get_health(),
    ) == (
        original[0] - 10,
        original[1] - 10,
    )

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell" and "hit_point_maximum_reduction" in str(action.value)
    )
    _ORCHESTRATOR.submit(state, action)

    assert (
        state.combat_rules.effective_maximum_health(state, "player").value,
        caster.get_health(),
    ) == original


def test_lesser_restoration_uses_magic_menu_bucket() -> None:
    bucket = action_bucket(
        ActionObservation(
            id="spell-lesser-restoration-player",
            label="Cast Lesser Restoration",
            kind="spell",
            creature_ref="player",
            cost={"bonus_action": 1},
            source_id="lesser_restoration",
            target_ref="player",
        ),
    )

    assert bucket == "magic"


def test_lesser_restoration_explicitly_selects_the_condition_to_remove() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.spell_slots_remaining[2] = 1
    for condition in ("blinded", "poisoned"):
        apply_encounter_effects(
            state,
            [
                EffectResult(
                    kind="apply_condition",
                    target_ref="player",
                    data={
                        "condition": condition,
                        "source_ref": "goblin_1",
                        "source_label": "Goblin",
                    },
                )
            ],
        )

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell" and str(action.value).endswith("#poisoned")
    )
    _ORCHESTRATOR.submit(state, action)

    assert state.has_condition("player", Condition.POISONED) is False
    assert state.has_condition("player", Condition.BLINDED) is True
