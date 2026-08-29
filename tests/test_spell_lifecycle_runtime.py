"""Exercise staged targeting, repeat saves, and spell-effect lifecycles."""

from dataclasses import replace
from typing import cast as type_cast

import pytest

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.spells import (
    load_spell_catalog,
)
from srd_arena.domain.effects import EffectResult
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.rule_effects import (
    ConditionImmunity,
    ConditionSaveAdvantage,
    DamageResistance,
    InvocationFailureChance,
    SpeedAdjustment,
)
from srd_arena.domain.effects.runtime import (
    EffectSource,
    EffectSourceKind,
    EndEventRule,
    OngoingEffect,
    OngoingEffectKind,
    OngoingEffectLifecycle,
    RepeatSaveLifecycle,
    RuntimeStateIdentity,
)
from srd_arena.domain.encounters import rule_queries
from srd_arena.domain.encounters.condition_state import remove_condition
from srd_arena.domain.encounters.creature_control import (
    creature_action_candidates,
    execute_creature_action,
)
from srd_arena.domain.encounters.effect_lifecycle.concentration import (
    resolve_concentration_damage,
)
from srd_arena.domain.encounters.effect_lifecycle.lifecycle_events import (
    resolve_spell_lifecycle_event,
)
from srd_arena.domain.encounters.effect_lifecycle.removal import (
    remove_ongoing_effects,
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
from srd_arena.domain.encounters.rule_queries import has_condition_save_advantage
from srd_arena.domain.encounters.state_runtime import apply_encounter_effects
from srd_arena.domain.encounters.turn_lifecycle import (
    active_movement_remaining,
    advance_turn,
)
from srd_arena.domain.geometry import Position
from srd_arena.infrastructure.scenarios import load_scenario_directory
from tests.encounter_runtime_support import (
    ORCHESTRATOR as _ORCHESTRATOR,
)
from tests.encounter_runtime_support import (
    TACTICAL_SCENARIO_DIR,
    is_spell_action,
    player_first_initiative,
    spell_payload,
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


def test_hold_person_applies_concentration_and_ends_after_repeated_save() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Hold Person",
            "XPHB",
            load_spell_catalog(SYSTEM_CONTENT_ROOT),
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 2
    state.creatures["goblin_1"].creature.statistics = replace(
        state.creatures["goblin_1"].creature.statistics,
        creature_type="humanoid",
    )
    state.creatures["goblin_1"].position.x = state.active_position.x + 1
    state.creatures["goblin_1"].position.y = state.active_position.y
    rolls = iter((1, 20))
    _use_deterministic_dice(session, die_roller=lambda _sides: next(rolls))

    action = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "hold_person", target_ref="goblin_1")
    )
    cast = _ORCHESTRATOR.submit(state, action)

    assert state.has_condition("goblin_1", Condition.PARALYZED) is True
    assert state.effective_conditions_for("goblin_1").has(Condition.INCAPACITATED)
    assert len(state.ongoing_effects) == 1
    assert state.ongoing_effects[0].kind.value == "concentration"
    paralyzed = next(
        condition
        for condition in state.conditions_for("goblin_1")
        if condition.condition is Condition.PARALYZED
    )
    assert paralyzed.identity.parent_id == state.ongoing_effects[0].identity.id
    assert paralyzed.identity.root_id == state.ongoing_effects[0].identity.id

    state.initiative_order = ["player", "goblin_1"]
    state.turn.index = 1
    advance_turn(state, cast)

    assert state.has_condition("goblin_1", Condition.PARALYZED) is False
    assert state.ongoing_effects == []
    assert ("turn", "Traveler's turn") in cast.messages
    assert any(
        "succeeds on the repeated Wisdom save" in text for _, text in cast.messages
    )


def test_one_target_repeat_save_does_not_end_multi_target_spell() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    effects = [
        EffectResult(
            kind="start_ongoing_effect",
            target_ref="goblin_1",
            data={
                "effect_kind": "concentration",
                "source_ref": "player",
                "source_label": "Caster",
                "definition_id": "hold_person",
                "target_refs": ["goblin_1", "goblin_2"],
            },
            lifecycle=OngoingEffectLifecycle(
                repeat_save=RepeatSaveLifecycle(
                    trigger="end_of_turn",
                    ability="wisdom",
                    dc=10,
                )
            ),
        ),
        *(
            EffectResult(
                kind="apply_condition",
                target_ref=target_ref,
                data={
                    "condition": "paralyzed",
                    "source_ref": "player",
                    "source_label": "Caster",
                    "source_kind": "spell",
                    "definition_id": "hold_person",
                    "parent_effect_kind": "concentration",
                },
            )
            for target_ref in ("goblin_1", "goblin_2")
        ),
    ]
    apply_encounter_effects(state, effects, origin_id="multi-target-cast")
    _use_deterministic_dice(session, die_roller=lambda _sides: 20)

    resolve_end_turn_effects(state, "goblin_1")

    assert state.has_condition("goblin_1", Condition.PARALYZED) is False
    assert state.has_condition("goblin_2", Condition.PARALYZED) is True
    assert state.ongoing_effects[0].target_refs == ("goblin_2",)


def test_ongoing_damage_resistance_is_removed_with_its_source() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "spell",
                    "source_ref": "player",
                    "source_label": "Caster",
                    "definition_id": "protection_from_poison",
                    "duration_rounds": 600,
                },
                rule_effects=(
                    DamageResistance(frozenset({"poison"})),
                    ConditionSaveAdvantage(frozenset({Condition.POISONED})),
                ),
            )
        ],
        origin_id="protection-cast",
    )

    assert "poison" in rule_queries.damage_resistances(state, "goblin_1").values
    assert has_condition_save_advantage(state, "goblin_1", ("poisoned",))

    remove_ongoing_effects(
        state,
        EffectResult(
            kind="remove_ongoing_effects",
            target_ref="goblin_1",
            data={"effect_id": state.ongoing_effects[0].identity.id},
        ),
    )

    assert "poison" not in rule_queries.damage_resistances(state, "goblin_1").values
    assert not has_condition_save_advantage(state, "goblin_1", ("poisoned",))


def test_condition_modifier_applies_to_repeated_saves() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "spell",
                    "source_ref": "player",
                    "source_label": "Protector",
                    "definition_id": "protection_from_poison",
                },
                rule_effects=(ConditionSaveAdvantage(frozenset({Condition.POISONED})),),
            )
        ],
        origin_id="protection-origin",
    )
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "spell",
                    "source_ref": "goblin_2",
                    "source_label": "Poisoner",
                    "definition_id": "persistent_poison",
                },
                lifecycle=OngoingEffectLifecycle(
                    repeat_save=RepeatSaveLifecycle(
                        trigger="end_of_turn",
                        ability="constitution",
                        dc=15,
                        failure_conditions=(Condition.POISONED,),
                    )
                ),
            ),
        ],
        origin_id="poison-origin",
    )
    rolls = iter([1, 20])
    _use_deterministic_dice(session, die_roller=lambda _sides: next(rolls))

    resolve_end_turn_effects(state, "goblin_1")

    assert [
        effect.identity.source.definition_id for effect in state.ongoing_effects
    ] == ["protection_from_poison"]


def test_speed_modifier_adjusts_current_movement_and_reverts() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    before = active_movement_remaining(state)
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="player",
                data={
                    "effect_kind": "spell",
                    "source_ref": "player",
                    "source_label": "Caster",
                    "definition_id": "longstrider",
                    "duration_rounds": 600,
                },
                rule_effects=(SpeedAdjustment(10),),
            )
        ],
        origin_id="longstrider-cast",
    )

    assert state.active_creature_state.movement_remaining == before + 2
    assert rule_queries.effective_speed(state, "player").value == 40

    remove_ongoing_effects(
        state,
        EffectResult(
            kind="remove_ongoing_effects",
            target_ref="player",
            data={"effect_id": state.ongoing_effects[0].identity.id},
        ),
    )

    assert state.active_creature_state.movement_remaining == before
    assert rule_queries.effective_speed(state, "player").value == 30


def test_heroism_immunity_and_turn_start_temporary_hit_points() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="apply_condition",
                target_ref="player",
                data={
                    "condition": "frightened",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            )
        ],
        origin_id="original-fear",
    )
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="player",
                data={
                    "effect_kind": "concentration",
                    "source_ref": "player",
                    "source_label": "Caster",
                    "definition_id": "heroism",
                    "duration_rounds": 10,
                },
                lifecycle=OngoingEffectLifecycle(turn_start_temporary_hit_points=4),
                rule_effects=(ConditionImmunity(frozenset({Condition.FRIGHTENED})),),
            )
        ],
        origin_id="heroism-cast",
    )

    assert state.has_condition("player", Condition.FRIGHTENED)
    state.conditions = [
        condition
        for condition in state.conditions
        if condition.condition is not Condition.FRIGHTENED
    ]
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="apply_condition",
                target_ref="player",
                data={
                    "condition": "frightened",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            ),
        ],
        origin_id="new-fear",
    )

    assert not state.has_condition("player", Condition.FRIGHTENED)
    assert state.creatures["player"].creature.temporary_hit_points == 0

    expire_ongoing_effects_for_turn_start(state, "player")

    assert state.creatures["player"].creature.temporary_hit_points == 4


def test_upcast_hold_person_stages_and_resolves_multiple_targets() -> None:
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
            "Hold Person", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[3] = 1
    for offset, target_ref in enumerate(("goblin_1", "goblin_2"), start=1):
        target = state.creatures[target_ref]
        target.creature.statistics = replace(
            target.creature.statistics,
            creature_type="humanoid",
        )
        target.position = Position(
            state.active_position.x + offset,
            state.active_position.y,
        )
    invalid_target = state.creatures["goblin_3"]
    invalid_target.creature.statistics = replace(
        invalid_target.creature.statistics,
        creature_type="construct",
    )
    invalid_target.position = Position(
        state.active_position.x + 3,
        state.active_position.y,
    )
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)

    initial = next(
        action
        for action in state.available_actions()
        if is_spell_action(
            action,
            "hold_person",
            target_ref="goblin_1",
            slot_level=3,
        )
    )
    opened = _ORCHESTRATOR.submit(state, initial)

    assert opened.paused_for_decision
    assert state.current_decision().kind == "spell_targets"
    assert caster.spellcasting.spell_slots_remaining[3] == 1
    assert not any(
        action.kind == "toggle_spell_target" and action.value == "goblin_3"
        for action in state.available_actions()
    )
    rejected = _ORCHESTRATOR.submit(
        state,
        EncounterAction(
            "Add invalid target",
            "toggle_spell_target",
            "goblin_3",
            id="crafted-invalid-spell-target",
            creature_ref="player",
        ),
    )
    assert rejected.events[-1].data["success"] is False
    assert rejected.events[-1].data["reason_code"] == ("target_creature_type_required")
    assert "creature types: humanoid" in rejected.messages[-1][1]
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
    resolved = _ORCHESTRATOR.submit(state, confirm)

    assert resolved.paused_for_decision is False
    assert state.current_decision().kind == "turn"
    assert caster.spellcasting.spell_slots_remaining[3] == 0
    assert state.has_condition("goblin_1", Condition.PARALYZED)
    assert state.has_condition("goblin_2", Condition.PARALYZED)
    assert state.ongoing_effects[0].target_refs == ("goblin_1", "goblin_2")


def test_scorching_ray_allocates_repeated_targets_without_enumerating_combinations() -> (
    None
):
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
            "Scorching Ray", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    _use_deterministic_dice(session, die_roller=lambda sides: 10 if sides == 20 else 3)

    initial = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "scorching_ray", target_ref="goblin_1")
    )
    opened = _ORCHESTRATOR.submit(state, initial)

    assert opened.paused_for_decision
    assert state.interrupts.pending_spell_cast is not None
    assert state.interrupts.pending_spell_cast.selected_target_refs == ["goblin_1"]
    assert not any(
        action.kind == "confirm_spell_targets" for action in state.available_actions()
    )

    for target_ref in ("goblin_1", "goblin_2"):
        add_ray = next(
            action
            for action in state.available_actions()
            if action.kind == "toggle_spell_target"
            and action.value == target_ref
            and action.id.endswith("-add")
        )
        _ORCHESTRATOR.submit(state, add_ray)

    assert state.interrupts.pending_spell_cast is not None
    assert state.interrupts.pending_spell_cast.selected_target_refs == [
        "goblin_1",
        "goblin_1",
        "goblin_2",
    ]

    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    resolved = _ORCHESTRATOR.submit(state, confirm)

    spell_event = next(event for event in resolved.events if event.type == "spell_cast")
    assert spell_event.data["target_refs"] == [
        "goblin_1",
        "goblin_1",
        "goblin_2",
    ]
    attack_roll_details = _sequence(spell_event.data["attack_roll_details"])
    assert len(attack_roll_details) == 3
    assert [_mapping(detail)["projectile_index"] for detail in attack_roll_details] == [
        1,
        2,
        3,
    ]
    assert len(_sequence(spell_event.data["damage_roll_details"])) == 3
    assert caster.spellcasting.spell_slots_remaining[2] == 0


def test_staged_spell_targeting_can_be_cancelled_without_spending_resources() -> None:
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
            "Scorching Ray", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    initial = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "scorching_ray", target_ref="goblin_1")
    )
    _ORCHESTRATOR.submit(state, initial)

    cancel = next(
        action
        for action in state.available_actions()
        if action.kind == "cancel_spell_targets"
    )
    _ORCHESTRATOR.submit(state, cancel)

    assert state.interrupts.pending_spell_cast is None
    assert state.current_decision().kind == "turn"
    assert caster.spellcasting.spell_slots_remaining[2] == 1
    assert state.active_actions_remaining == 1


def test_ray_of_sickness_combines_scaled_damage_and_timed_condition() -> None:
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
            "Ray of Sickness", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    _use_deterministic_dice(session, die_roller=lambda sides: 15 if sides == 20 else 2)

    action = next(
        action
        for action in state.available_actions()
        if is_spell_action(
            action,
            "ray_of_sickness",
            target_ref="goblin_1",
            slot_level=2,
        )
    )
    resolved = _ORCHESTRATOR.submit(state, action)

    spell_event = next(event for event in resolved.events if event.type == "spell_cast")
    damage_roll_detail = _mapping(spell_event.data["damage_roll_detail"])
    assert damage_roll_detail["dice"] == "3d8"
    assert state.has_condition("goblin_1", Condition.POISONED)


def test_eldritch_blast_uses_caster_level_for_beam_allocation() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.attributes = replace(caster.attributes, level=11)
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Eldritch Blast", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    _use_deterministic_dice(session, die_roller=lambda sides: 20 if sides == 20 else 4)

    initial = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "eldritch_blast", target_ref="goblin_1")
    )
    _ORCHESTRATOR.submit(state, initial)

    assert state.interrupts.pending_spell_cast is not None
    assert state.interrupts.pending_spell_cast.maximum_targets == 3
    for target_ref in ("goblin_1", "goblin_2"):
        add_beam = next(
            action
            for action in state.available_actions()
            if action.kind == "toggle_spell_target"
            and action.value == target_ref
            and action.id.endswith("-add")
        )
        _ORCHESTRATOR.submit(state, add_beam)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    resolved = _ORCHESTRATOR.submit(state, confirm)

    spell_event = next(event for event in resolved.events if event.type == "spell_cast")
    assert spell_event.data["target_refs"] == [
        "goblin_1",
        "goblin_1",
        "goblin_2",
    ]
    assert len(_sequence(spell_event.data["attack_roll_details"])) == 3
    assert len(_sequence(spell_event.data["damage_roll_details"])) == 3


def test_ice_knife_explodes_on_a_miss_and_scales_only_cold_damage() -> None:
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
            "Ice Knife", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    state.active_position.x = 1
    state.active_position.y = 1
    state.creatures["goblin_1"].position = Position(5, 5)
    state.creatures["goblin_2"].position = Position(6, 5)
    state.creatures["goblin_3"].position = Position(10, 10)
    _use_deterministic_dice(session, die_roller=lambda sides: 1 if sides == 20 else 2)

    ice_knife_actions = [
        action
        for action in state.available_actions()
        if is_spell_action(action, "ice_knife")
    ]
    assert ice_knife_actions
    action = next(
        action
        for action in ice_knife_actions
        if is_spell_action(
            action,
            "ice_knife",
            target_ref="goblin_1",
            slot_level=2,
        )
    )
    resolved = _ORCHESTRATOR.submit(state, action)

    spell_event = next(event for event in resolved.events if event.type == "spell_cast")
    damage_roll_details = [
        _mapping(detail)
        for detail in _sequence(spell_event.data["damage_roll_details"])
    ]
    primary = next(
        detail for detail in damage_roll_details if detail["damage_type"] == "piercing"
    )
    cold = [detail for detail in damage_roll_details if detail["damage_type"] == "cold"]
    assert primary["dice"] == "1d10"
    assert primary["final_damage"] == 0
    assert {detail["target_ref"] for detail in cold} == {"goblin_1", "goblin_2"}
    assert all(detail["dice"] == "3d6" for detail in cold)


def test_weird_deals_damage_on_a_failed_repeat_save() -> None:
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
            "Weird", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[9] = 1
    state.active_position.x = 1
    state.active_position.y = 1
    target = state.creatures["goblin_1"]
    target.position = Position(8, 8)
    target.creature.current_health = 200
    state.creatures["goblin_2"].position = Position(15, 1)
    state.creatures["goblin_3"].position = Position(15, 10)
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)

    _choose_directional_spell(session, "Cast Weird", (8, 8))

    assert state.has_condition("goblin_1", Condition.FRIGHTENED)
    health_after_cast = target.creature.get_health()
    resolve_end_turn_effects(state, "goblin_1")
    assert target.creature.get_health() == health_after_cast - 5


def test_sleep_progresses_from_incapacitated_to_unconscious() -> None:
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
            "Sleep", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    state.creatures["goblin_1"].position.x = state.active_position.x + 2
    state.creatures["goblin_1"].position.y = state.active_position.y
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)

    _choose_directional_spell(
        session,
        "Cast Sleep",
        (
            state.creatures["goblin_1"].position.x,
            state.creatures["goblin_1"].position.y,
        ),
    )

    assert state.has_condition("goblin_1", Condition.INCAPACITATED)
    state.initiative_order = ["player", "goblin_1"]
    state.turn.index = 1
    advance_turn(state, EncounterProgress())
    assert state.has_condition("goblin_1", Condition.UNCONSCIOUS)
    assert state.has_condition("goblin_1", Condition.INCAPACITATED) is False


def test_sleep_stages_choice_when_area_contains_multiple_creatures() -> None:
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
            "Sleep", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    origin = Position(state.active_position.x + 2, state.active_position.y)
    state.creatures["goblin_1"].position = origin
    state.creatures["goblin_2"].position = Position(origin.x, origin.y + 1)
    state.creatures["goblin_3"].creature.current_health = 0
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)

    _choose_directional_spell(
        session,
        "Cast Sleep",
        (origin.x, origin.y),
    )
    assert state.current_decision().kind == "spell_targets"
    remove_second = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target" and action.value == "goblin_2"
    )
    _ORCHESTRATOR.submit(state, remove_second)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    _ORCHESTRATOR.submit(state, confirm)

    assert state.has_condition("goblin_1", Condition.INCAPACITATED)
    assert state.has_condition("goblin_2", Condition.INCAPACITATED) is False


@pytest.mark.parametrize(
    ("statistics_change", "reason"),
    [
        (
            {"condition_immunities": frozenset({Condition.EXHAUSTION})},
            "Sleep: immune to exhaustion",
        ),
        (
            {"mechanical_traits": frozenset({"does_not_sleep"})},
            "Sleep: does_not_sleep",
        ),
    ],
)
def test_sleep_automatically_spares_ineligible_creature(
    statistics_change: dict[str, object],
    reason: str,
) -> None:
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
            "Sleep", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    target = state.creatures["goblin_1"]
    target.position.x = state.active_position.x + 2
    target.position.y = state.active_position.y
    if "condition_immunities" in statistics_change:
        target.creature.statistics = replace(
            target.creature.statistics,
            condition_immunities=type_cast(
                frozenset[Condition],
                statistics_change["condition_immunities"],
            ),
        )
    else:
        target.creature.statistics = replace(
            target.creature.statistics,
            mechanical_traits=type_cast(
                frozenset[str],
                statistics_change["mechanical_traits"],
            ),
        )
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)

    cast = _choose_directional_spell(
        session,
        "Cast Sleep",
        (target.position.x, target.position.y),
    )

    assert state.has_condition("goblin_1", Condition.INCAPACITATED) is False
    save = _mapping(
        next(
            _sequence(event.data["save_details"])[0]
            for event in cast.events
            if event.type == "spell_cast"
        )
    )
    assert save["automatic_success_reasons"] == [reason]
    assert "die" not in save
    assert any(
        f"is unaffected by Sleep: {reason}" in text for _channel, text in cast.messages
    )


def test_charm_person_save_has_advantage_against_opponent() -> None:
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
            "Charm Person", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[1] = 1
    target = state.creatures["goblin_1"]
    target.creature.statistics = replace(
        target.creature.statistics,
        creature_type="humanoid",
    )
    target.position.x = state.active_position.x + 1
    target.position.y = state.active_position.y
    rolls = iter((1, 20))
    _use_deterministic_dice(session, die_roller=lambda _sides: next(rolls))

    action = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "charm_person", target_ref="goblin_1")
    )
    cast = _ORCHESTRATOR.submit(state, action)

    assert state.has_condition("goblin_1", Condition.CHARMED) is False
    save = _mapping(
        next(
            _sequence(event.data["save_details"])[0]
            for event in cast.events
            if event.type == "spell_cast"
        )
    )
    assert save["die"] == 20


def test_adjacent_creature_can_spend_action_to_wake_sleep_target() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "concentration",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "definition_id": "sleep",
                },
                lifecycle=OngoingEffectLifecycle(
                    end_events=(EndEventRule("adjacent_creature_wakes_target", "any"),)
                ),
            ),
            EffectResult(
                kind="apply_condition",
                target_ref="goblin_1",
                data={
                    "condition": "unconscious",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "source_kind": "spell",
                    "definition_id": "sleep",
                },
            ),
        ],
        origin_id="sleep-cast",
    )
    state.creatures["goblin_2"].position = Position(
        state.creatures["goblin_1"].position.x + 1,
        state.creatures["goblin_1"].position.y,
    )
    state.initiative_order = ["goblin_2", "player", "goblin_1"]
    state.turn.index = 0

    action = next(
        action
        for action in creature_action_candidates(state, "goblin_2")
        if action.kind == "wake_spell_target" and action.value == "goblin_1"
    )
    result = execute_creature_action(state, action, state.current_decision())

    assert state.has_condition("goblin_1", Condition.UNCONSCIOUS) is False
    assert state.creatures["goblin_2"].actions_remaining == 0
    assert any("wakes" in text for _, text in result.progress.messages)


@pytest.mark.parametrize(
    ("definition_id", "condition", "event"),
    [
        ("invisibility", "invisible", "target_makes_attack"),
        ("sleep", "unconscious", "target_damaged"),
    ],
)
def test_spell_lifecycle_event_ends_effect_for_affected_target(
    definition_id: str,
    condition: str,
    event: str,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    target_ref = "goblin_1"
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref=target_ref,
                data={
                    "effect_kind": "spell",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "definition_id": definition_id,
                },
                lifecycle=OngoingEffectLifecycle(
                    end_events=(EndEventRule(event, "any"),)
                ),
            ),
            EffectResult(
                kind="apply_condition",
                target_ref=target_ref,
                data={
                    "condition": condition,
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "source_kind": "spell",
                    "definition_id": definition_id,
                },
            ),
        ],
        origin_id=f"{definition_id}-cast",
    )

    resolve_spell_lifecycle_event(
        state,
        event,
        actor_ref=target_ref if event != "target_damaged" else "player",
        target_ref=target_ref,
    )

    assert state.ongoing_effects == []
    assert state.conditions_for(target_ref) == ()


def test_charm_ends_only_when_source_side_damages_target() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "spell",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "definition_id": "charm_person",
                },
                lifecycle=OngoingEffectLifecycle(
                    end_events=(EndEventRule("target_damaged", "source_team"),)
                ),
            ),
            EffectResult(
                kind="apply_condition",
                target_ref="goblin_1",
                data={
                    "condition": "charmed",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "source_kind": "spell",
                    "definition_id": "charm_person",
                },
            ),
        ],
        origin_id="charm-cast",
    )

    resolve_spell_lifecycle_event(
        state,
        "target_damaged",
        actor_ref="goblin_2",
        target_ref="goblin_1",
    )
    assert state.has_condition("goblin_1", Condition.CHARMED)

    resolve_spell_lifecycle_event(
        state,
        "target_damaged",
        actor_ref="player",
        target_ref="goblin_1",
    )
    assert state.has_condition("goblin_1", Condition.CHARMED) is False


def test_hideous_laughter_damage_save_has_advantage() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "concentration",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "definition_id": "hideous_laughter",
                },
                lifecycle=OngoingEffectLifecycle(
                    repeat_save=RepeatSaveLifecycle(
                        trigger="end_of_turn",
                        ability="wisdom",
                        dc=15,
                        damage_grants_advantage=True,
                    )
                ),
            ),
            EffectResult(
                kind="apply_condition",
                target_ref="goblin_1",
                data={
                    "condition": "incapacitated",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "source_kind": "spell",
                    "definition_id": "hideous_laughter",
                },
            ),
        ],
        origin_id="laughter-cast",
    )
    rolls = iter((1, 20))
    _use_deterministic_dice(session, die_roller=lambda _sides: next(rolls))

    resolve_spell_lifecycle_event(
        state,
        "target_damaged",
        actor_ref="player",
        target_ref="goblin_1",
    )

    assert state.ongoing_effects == []
    assert state.has_condition("goblin_1", Condition.INCAPACITATED) is False


def test_hideous_laughter_prevents_target_from_removing_its_own_prone() -> None:
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
            "Hideous Laughter",
            "XPHB",
            load_spell_catalog(SYSTEM_CONTENT_ROOT),
        )
    )
    caster.spellcasting.spell_slots_remaining[1] = 1
    state.creatures["goblin_1"].position = Position(
        state.active_position.x + 1,
        state.active_position.y,
    )
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)
    action = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "hideous_laughter", target_ref="goblin_1")
    )
    _ORCHESTRATOR.submit(state, action)

    remove_condition(
        state,
        "goblin_1",
        Condition.PRONE,
        removed_by_ref="goblin_1",
    )
    assert state.has_condition("goblin_1", Condition.PRONE)

    remove_condition(state, "goblin_1", Condition.PRONE)
    assert state.has_condition("goblin_1", Condition.PRONE) is False


def test_hideous_laughter_success_is_reported_as_a_save() -> None:
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
            "Hideous Laughter",
            "XPHB",
            load_spell_catalog(SYSTEM_CONTENT_ROOT),
        )
    )
    caster.spellcasting.spell_slots_remaining[1] = 1
    state.creatures["goblin_1"].position = Position(
        state.active_position.x + 1,
        state.active_position.y,
    )
    _use_deterministic_dice(session, die_roller=lambda _sides: 20)
    action = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "hideous_laughter", target_ref="goblin_1")
    )

    result = _ORCHESTRATOR.submit(state, action)

    assert state.has_condition("goblin_1", Condition.INCAPACITATED) is False
    assert any(
        "resists Hideous Laughter with a successful Wisdom save" in text
        for _channel, text in result.messages
    )
    assert not any("does not affect" in text for _channel, text in result.messages)


def test_new_concentration_replaces_the_previous_effect_tree() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state

    for origin_id, target_ref in (
        ("first-cast", "goblin_1"),
        ("second-cast", "goblin_2"),
    ):
        apply_encounter_effects(
            state,
            [
                EffectResult(
                    kind="start_ongoing_effect",
                    target_ref=target_ref,
                    data={
                        "effect_kind": "concentration",
                        "source_ref": "player",
                        "source_label": "Traveler",
                        "definition_id": "hold_person",
                    },
                ),
                EffectResult(
                    kind="apply_condition",
                    target_ref=target_ref,
                    data={
                        "condition": "paralyzed",
                        "source_ref": "player",
                        "source_label": "Traveler",
                        "source_kind": "spell",
                        "definition_id": "hold_person",
                    },
                ),
            ],
            origin_id=origin_id,
        )

    assert state.has_condition("goblin_1", Condition.PARALYZED) is False
    assert state.has_condition("goblin_2", Condition.PARALYZED) is True
    assert len(state.ongoing_effects) == 1
    assert state.ongoing_effects[0].identity.source.origin_id == "second-cast"


def test_casting_a_new_concentration_spell_logs_the_dropped_spell() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.extend(
        (
            _build_referenced_spell(
                "Hold Person", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
            ),
            _build_referenced_spell(
                "Protection from Energy",
                "XPHB",
                load_spell_catalog(SYSTEM_CONTENT_ROOT),
            ),
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    caster.spellcasting.spell_slots_remaining[3] = 1
    state.creatures["goblin_1"].creature.statistics = replace(
        state.creatures["goblin_1"].creature.statistics,
        creature_type="humanoid",
    )
    state.creatures["goblin_1"].position = Position(
        state.active_position.x + 1,
        state.active_position.y,
    )
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)
    hold = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "hold_person", target_ref="goblin_1")
    )
    _ORCHESTRATOR.submit(state, hold)
    state.creatures["player"].actions_remaining = 1
    state.creatures["player"].magic_actions_remaining = 1
    protection = next(
        action
        for action in state.available_actions()
        if is_spell_action(action, "protection_from_energy", target_ref="player")
        and spell_payload(action).selected_damage_type == "fire"
    )

    result = _ORCHESTRATOR.submit(state, protection)

    assert (
        "system",
        f"{caster.name} drops concentration on Hold Person.",
    ) in result.messages
    assert state.has_condition("goblin_1", Condition.PARALYZED) is False
    assert state.ongoing_effects[0].label == "Protection from Energy"


def test_somatic_invocation_failure_spends_resources_before_resolution() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster_ref = state.current_decision().creature_ref
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Cure Wounds",
            "XPHB",
            load_spell_catalog(SYSTEM_CONTENT_ROOT),
        )
    )
    caster.spellcasting.spell_slots_remaining[1] = 1
    caster.current_health = caster.get_max_health() - 5
    slow = OngoingEffect(
        identity=RuntimeStateIdentity(
            id="ongoing:slow:test",
            source=EffectSource(
                kind=EffectSourceKind.SPELL,
                definition_id="slow",
                applied_by_ref="goblin_1",
                label="Slow",
                origin_id="slow:test",
            ),
        ),
        target_refs=(caster_ref,),
        kind=OngoingEffectKind.SPELL,
        rule_effects=(
            InvocationFailureChance(
                invocation_kinds=frozenset({"cast_spell"}),
                required_components=frozenset({"somatic"}),
                numerator=1,
                denominator=4,
                code="slow.somatic_spell_failure",
                message="The spell fails because its gestures are too slow.",
            ),
        ),
    )
    state.ongoing_effects.append(slow)
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)
    initial_health = caster.get_health()
    action = next(
        candidate
        for candidate in state.available_actions()
        if is_spell_action(candidate, "cure_wounds")
    )

    result = _ORCHESTRATOR.submit(state, action)

    assert caster.get_health() == initial_health
    assert caster.spellcasting.spell_slots_remaining[1] == 0
    assert state.active_actions_remaining == 0
    assert not any(event.type == "spell_cast" for event in result.events)
    check = next(
        event for event in result.events if event.type == "invocation_start_checked"
    )
    assert check.data["allowed"] is False
    assert check.data["components"] == ["somatic", "verbal"]
    assert check.data["checks"] == [
        {
            "provider_state_id": slow.identity.id,
            "source": {
                "kind": "spell",
                "definition_id": "slow",
                "applied_by_ref": "goblin_1",
                "label": "Slow",
                "origin_id": "slow:test",
            },
            "code": "slow.somatic_spell_failure",
            "message": "The spell fails because its gestures are too slow.",
            "numerator": 1,
            "denominator": 4,
            "roll": 1,
            "failed": True,
        }
    ]
    assert (
        "system",
        "The spell fails because its gestures are too slow.",
    ) in result.messages


def test_failed_damage_save_ends_concentration_and_its_conditions() -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    apply_encounter_effects(
        state,
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "concentration",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "definition_id": "hold_person",
                },
            ),
            EffectResult(
                kind="apply_condition",
                target_ref="goblin_1",
                data={
                    "condition": "paralyzed",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "source_kind": "spell",
                    "definition_id": "hold_person",
                },
            ),
        ],
        origin_id="hold-cast",
    )
    _use_deterministic_dice(session, die_roller=lambda _sides: 1)

    progress = EncounterProgress()
    resolve_concentration_damage(state, "player", 20, progress)

    assert state.ongoing_effects == []
    assert state.has_condition("goblin_1", Condition.PARALYZED) is False
    assert (
        "system",
        "Traveler loses concentration on Hold Person (Constitution 9 vs DC 10).",
    ) in progress.messages
