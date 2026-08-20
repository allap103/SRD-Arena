from pathlib import Path
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from srd_arena.domain.encounters.encounter import (
    ActionCost,
    EncounterAction,
    EncounterState,
)
from srd_arena.domain.encounters.actions.hit_effects import (
    apply_attack_hit_effects,
)
from srd_arena.domain.encounters.actions.stat_block import (
    recharge_stat_block_actions,
)
from srd_arena.domain.encounters.models import EncounterProgress
from srd_arena.domain.encounters.ongoing_effects import (
    expire_ongoing_effects_for_turn_start,
    resolve_concentration_damage,
    resolve_end_turn_effects,
    resolve_spell_lifecycle_event,
)
from srd_arena.frontends.shared.combat import render_encounter_text
from srd_arena.runtime.scenario import Scenario
from srd_arena.frontends.qt.app import GameWindow
from srd_arena.domain.effects import EffectResult
from srd_arena.domain.effects.application import condition_from_effect
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.effects.runtime import UntilTurnStart
from srd_arena.domain.geometry import Position
from srd_arena.domain.rolls.saving_throws import resolve_saving_throw
from srd_arena.domain.spells.rules import (
    parse_spell_action_slot,
    parse_spell_action_value,
    spell_action_value,
)
from srd_arena.domain.creatures import (
    ActionTarget,
    ActionResource,
    ActionOutcomeStage,
    AutomaticActionDefinition,
    AttackActionDefinition,
    DamageEffect,
    ConditionEffect,
    ConditionRequirement,
    CreatureTypeRequirement,
    SavingThrowActionDefinition,
)
from srd_arena.frontends.shared.session import (
    SpellSlotTrackView,
    build_session_presentation,
)
from srd_arena.runtime.models import ActionView
from srd_arena.content.catalogs import load_bestiary_catalog, load_spell_catalog
from srd_arena.content.loaders.creatures import build_creature
from srd_arena.content.translators import build_spell
from srd_arena.content.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.schemas import CreatureSchema
from srd_arena.frontends.qt.ui.encounter import BattlefieldWidget
from srd_arena.frontends.qt.ui.encounter.config import (
    ActionMenuScope,
    TargetSelectionMode,
)

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
TACTICAL_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "tactical_game"
MULTIATTACK_SCENARIO_DIR = Path(__file__).parents[1] / "content" / "scenarios" / "multiattack_showcase"
STAT_BLOCK_ACTION_SCENARIO_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "scenarios"
    / "stat_block_action_showcase"
)
CONDITIONS_SHOWCASE_SCENARIO_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "scenarios"
    / "conditions_showcase"
)
_ROLL_INITIATIVE = EncounterState._roll_initiative


@pytest.fixture(autouse=True)
def _player_first_initiative(monkeypatch):
    def _fixed_initiative(self):
        self.initiative_entries = []
        first_external_ref = next(
            creature_ref for creature_ref in self.creatures if self._creature_controller(creature_ref) == "external"
        )
        self.initiative_order = [
            first_external_ref,
            *(creature_ref for creature_ref in self.creatures if creature_ref != first_external_ref),
        ]

    monkeypatch.setattr(EncounterState, "_roll_initiative", _fixed_initiative)


def _action_id_by_label(session, label: str) -> str:
    return next(
        action.id
        for action in session.get_scene_view().action_details
        if action.label == label
    )


def _action_labels(session) -> list[str]:
    return [action.label for action in session.get_scene_view().action_details]


def _action_id_by_prefix(session, prefix: str) -> str:
    return next(
        action.id
        for action in session.get_scene_view().action_details
        if action.label.startswith(prefix)
    )


def _action_id(session, kind: str, value: object) -> str:
    return next(
        action.id
        for action in session.get_scene_view().action_details
        if action.kind == kind and action.value == value
    )


def _choose_directional_spell(session, label: str, aim_cell: tuple[int, int]):
    scene_view = session.get_scene_view()
    action = next(detail for detail in scene_view.action_details if detail.label == label)
    return session.choose_encounter_action(
        EncounterAction(
            label=action.label,
            kind=action.kind,
            value=spell_action_value(
                parse_spell_action_value(str(action.value))[0],
                aim_point=(aim_cell[0] + 0.5, aim_cell[1] + 0.5),
                slot_level=parse_spell_action_slot(str(action.value)),
            ),
            id=action.id,
            creature_ref=action.creature_ref,
            cost=ActionCost(
                movement=action.cost.get("movement", 0),
                action=action.cost.get("action", 0),
                bonus_action=action.cost.get("bonus_action", 0),
                reaction=action.cost.get("reaction", 0),
            ),
            source_trigger_id=action.source_trigger_id,
        )
    )


def test_goblin_encounter_scene_generates_runtime_actions() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    scene_view = session.get_scene_view()
    assert scene_view.scene_text is None
    labels = [action.label for action in scene_view.action_details]
    assert "Move up" in labels
    assert "Move up-right" in labels
    assert "Wait" in labels
    assert "Flee encounter" not in labels
    assert "Retreat until the encounter system is ready." not in labels
    assert "Save game" not in labels
    assert "Load game" not in labels
    assert labels[-1] == "Exit game"


def test_stat_block_action_showcase_exposes_new_runtime_capabilities() -> None:
    scenario = Scenario(str(STAT_BLOCK_ACTION_SCENARIO_DIR))
    session = scenario.create_session()
    session.current_scene_id = "stat_block_action_showcase"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state

    avatar_actions = state._available_creature_actions("avatar")
    wyrmling_actions = state._available_creature_actions("blue_wyrmling")
    assassin_actions = state._creature_action_candidates("assassin")

    assert scenario.display_name == "Executable Stat-Block Actions"
    assert any(
        action.preferred_attack_name == "Reaping Scythe"
        for action in avatar_actions
    )
    assert any(
        action.preferred_attack_name == "Lightning Breath {@recharge 5}"
        for action in wyrmling_actions
    )
    [assassin_multiattack] = [
        action for action in assassin_actions if action.kind == "multiattack"
    ]
    assert assassin_multiattack.label == "Multiattack"
    assert state.creatures["assassin"].creature.multiattack is not None
    [assassin_slots] = (
        state.creatures["assassin"]
        .creature.multiattack.executable_slot_plans(
            {"Shortsword", "Light Crossbow"}
        )
    )
    assert len(assassin_slots) == 3
    assert all(
        {option.name for option in slot.options}
        == {"Shortsword", "Light Crossbow"}
        for slot in assassin_slots
    )


def test_unenriched_frostwing_breath_is_present_as_unimplemented() -> None:
    session = Scenario(str(MULTIATTACK_SCENARIO_DIR)).create_session()
    session.current_scene_id = "multiattack_showcase"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.initiative_order = ["player", "air_elemental", "aboleth"]
    state.current_turn_index = 0

    cold_breath = next(
        action
        for action in session.get_scene_view().action_details
        if action.label == "Cold Breath"
    )

    assert cold_breath.enabled is False
    assert cold_breath.availability == "unimplemented"
    assert cold_breath.unavailable_reasons == (
        "No structured mechanics are available for this action.",
    )


def test_targeted_action_labels_only_name_the_action() -> None:
    session = Scenario(str(STAT_BLOCK_ACTION_SCENARIO_DIR)).create_session()
    session.current_scene_id = "stat_block_action_showcase"
    session.get_scene_view()
    assert session.encounter_state is not None

    actions = session.encounter_state._available_creature_actions("avatar")

    assert all(
        action.label == action.preferred_attack_name
        for action in actions
        if action.kind in {"attack", "stat_block"}
    )
    assert all(
        action.label == "Grapple"
        for action in actions
        if action.kind == "grapple"
    )


def test_line_stat_block_action_can_be_aimed_at_a_map_point(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    actor_ref = state.current_decision().creature_ref
    actor = state.creatures[actor_ref]
    target_refs = [
        creature_ref
        for creature_ref in state.creatures
        if state._creatures_are_opponents(actor_ref, creature_ref)
    ][:2]
    assert len(target_refs) == 2
    actor.position = Position(0, 1)
    state.creatures[target_refs[0]].position = Position(2, 1)
    state.creatures[target_refs[1]].position = Position(2, 2)
    actor.creature.stat_block_actions["Lightning Breath"] = (
        SavingThrowActionDefinition(
            name="Lightning Breath",
            target=ActionTarget(
                kind="area",
                shape="line",
                size_feet=30,
                width_feet=10,
            ),
            ability="dex",
            dc=30,
            failure=(
                ActionOutcomeStage(
                    effects=(DamageEffect("1d6", 0, "lightning"),),
                ),
            ),
            success=(),
            success_damage="half",
            always=(),
        )
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda count, sides: count * sides,
    )
    health_before = {
        target_ref: state.creatures[target_ref].creature.get_health()
        for target_ref in target_refs
    }
    action = EncounterAction(
        label="Lightning Breath",
        kind="stat_block",
        value=(5.5, 1.5),
        id=f"{actor_ref}-lightning-breath",
        creature_ref=actor_ref,
        preferred_attack_name="Lightning Breath",
        cost=ActionCost(action=1),
    )

    state._execute_creature_action(action, state.current_decision())

    assert all(
        state.creatures[target_ref].creature.get_health()
        == health_before[target_ref] - 6
        for target_ref in target_refs
    )


def test_automatic_stat_block_damage_action_is_discovered_and_resolved(
    monkeypatch,
) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    actor_ref = state.current_decision().creature_ref
    target_ref = next(
        creature_ref
        for creature_ref in state.creatures
        if state._creatures_are_opponents(actor_ref, creature_ref)
    )
    actor = state.creatures[actor_ref]
    target = state.creatures[target_ref]
    actor.position = Position(0, 0)
    target.position = Position(1, 0)
    actor.creature.stat_block_actions["Reaping Scythe"] = (
        AutomaticActionDefinition(
            name="Reaping Scythe",
            target=ActionTarget(kind="creature", range_feet=5),
            effects=(DamageEffect("1d8", 3, "slashing"),),
            resource=ActionResource(
                kind="uses",
                maximum=1,
                reset="day",
            ),
        )
    )
    actor.creature.stat_block_action_resources["Reaping Scythe"] = 1
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda count, sides: count * sides,
    )
    action = next(
        action
        for action in state._available_creature_actions(actor_ref)
        if action.preferred_attack_name == "Reaping Scythe"
    )
    health_before = target.creature.get_health()

    result = state._execute_creature_action(
        action,
        state.current_decision(),
    )

    assert target.creature.get_health() == max(0, health_before - 11)
    assert actor.actions_remaining == 0
    assert actor.creature.stat_block_action_resources["Reaping Scythe"] == 0
    assert any(
        event.type == "stat_block_action_resolved"
        for event in result.progress.events
    )
    actor.actions_remaining = 1
    assert not any(
        action.preferred_attack_name == "Reaping Scythe"
        for action in state._available_creature_actions(actor_ref)
    )


def test_saving_throw_stat_block_action_resolves_damage_and_half_on_save(
    monkeypatch,
) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    actor_ref = state.current_decision().creature_ref
    target_ref = next(
        creature_ref
        for creature_ref in state.creatures
        if state._creatures_are_opponents(actor_ref, creature_ref)
    )
    actor = state.creatures[actor_ref]
    target = state.creatures[target_ref]
    actor.position = Position(0, 0)
    target.position = Position(1, 0)
    actor.creature.stat_block_actions["Acid Spray"] = (
        SavingThrowActionDefinition(
            name="Acid Spray",
            target=ActionTarget(kind="creature", range_feet=5),
            ability="dex",
            dc=20,
            failure=(
                ActionOutcomeStage(
                    effects=(DamageEffect("2d6", 0, "acid"),),
                ),
            ),
            success=(),
            success_damage="half",
            always=(),
        )
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda count, sides: count * sides,
    )
    action = next(
        action
        for action in state._available_creature_actions(actor_ref)
        if action.preferred_attack_name == "Acid Spray"
    )
    health_before = target.creature.get_health()

    result = state._execute_creature_action(
        action,
        state.current_decision(),
    )

    assert target.creature.get_health() == max(0, health_before - 12)
    event = next(
        event
        for event in result.progress.events
        if event.type == "stat_block_action_resolved"
    )
    [outcome] = event.data["outcomes"]
    assert outcome["success"] is False
    assert outcome["damage"] == min(12, health_before)


def test_unsupported_stat_block_effect_is_rejected_before_execution() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    actor_ref = state.current_decision().creature_ref
    target_ref = next(
        creature_ref
        for creature_ref in state.creatures
        if state._creatures_are_opponents(actor_ref, creature_ref)
    )
    actor = state.creatures[actor_ref]
    actor.creature.stat_block_actions["Paralyze"] = (
        AutomaticActionDefinition(
            name="Paralyze",
            target=ActionTarget(kind="creature", range_feet=5),
            effects=(ConditionEffect("paralyzed"),),
        )
    )
    action = EncounterAction(
        "Paralyze",
        "stat_block",
        target_ref,
        id="paralyze",
        creature_ref=actor_ref,
        preferred_attack_name="Paralyze",
        cost=ActionCost(action=1),
    )

    eligibility = state.action_eligibility(action)

    assert eligibility.allowed is False
    assert eligibility.failures[-1].code == "unsupported_stat_block_mechanics"
    assert actor.actions_remaining == 1


def test_recharge_stat_block_resource_becomes_available_on_required_roll(
    monkeypatch,
) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    creature = session.encounter_state.active_creature_state.creature
    creature.stat_block_actions["Breath"] = AutomaticActionDefinition(
        name="Breath",
        target=ActionTarget(kind="creature", range_feet=5),
        effects=(DamageEffect("1d6", 0, "fire"),),
        resource=ActionResource(kind="recharge", minimum=5),
    )
    creature.stat_block_action_resources["Breath"] = 0
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 5,
    )

    recharge_stat_block_actions(creature)

    assert creature.stat_block_action_resources["Breath"] == 1


def test_action_eligibility_exposes_structured_failures() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    actor_ref = state.current_decision().creature_ref
    state.conditions.append(
        build_applied_condition(
            condition=Condition.STUNNED,
            source_ref="goblin_1",
            source_label="Goblin Warrior",
            target_ref=actor_ref,
        )
    )
    move = EncounterAction(
        "Move right",
        "move",
        "right",
        id=f"{actor_ref}-move-right",
        creature_ref=actor_ref,
        cost=ActionCost(movement=1),
    )

    eligibility = state.action_eligibility(move)

    assert eligibility.allowed is False
    assert {failure.code for failure in eligibility.failures} == {
        "condition.cannot_take_actions"
    }
    assert all(action.kind == "wait" for action in state.available_actions())


def test_paralyzed_blocks_actions_through_effective_incapacitation() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    actor_ref = state.current_decision().creature_ref
    paralyzed = build_applied_condition(
        condition=Condition.PARALYZED,
        source_ref="goblin_1",
        source_label="Goblin Warrior",
        target_ref=actor_ref,
    )
    state.conditions.append(paralyzed)
    move = next(
        action
        for action in state._creature_action_candidates(actor_ref)
        if action.kind == "move"
    )

    eligibility = state.action_eligibility(move)

    assert eligibility.allowed is False
    assert eligibility.failures[0].code == "condition.cannot_take_actions"
    assert eligibility.failures[0].state_ids == (paralyzed.id,)
    effective = state.effective_conditions_for(actor_ref)
    assert effective.has(Condition.INCAPACITATED)
    assert state.has_condition(actor_ref, Condition.INCAPACITATED) is False


def test_close_attack_against_paralyzed_target_has_advantage_and_is_critical(
    monkeypatch,
) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    attacker_ref = state.current_decision().creature_ref
    target_ref = "goblin_1"
    state.creatures[target_ref].position.x = state.active_position.x + 1
    state.creatures[target_ref].position.y = state.active_position.y
    paralyzed = build_applied_condition(
        condition=Condition.PARALYZED,
        source_ref=attacker_ref,
        source_label=state._creature_label(attacker_ref),
        target_ref=target_ref,
    )
    state.conditions.append(paralyzed)
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 10,
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda count, _sides: count,
    )

    attack = next(
        action
        for action in state.available_actions()
        if action.kind == "attack" and action.value == target_ref
    )
    result = state.apply_action(attack)
    event = next(event for event in result.events if event.type == "attack_resolved")

    assert event.data["attack_roll_detail"]["mode"] == "advantage"
    assert event.data["critical_hit"] is True
    assert event.data["attack_roll_detail"][
        "automatic_critical_provider_ids"
    ] == [paralyzed.id]


def test_paralyzed_target_automatically_fails_strength_and_dexterity_saves() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    target_ref = "goblin_1"
    paralyzed = build_applied_condition(
        condition=Condition.PARALYZED,
        source_ref="player",
        source_label="Traveler",
        target_ref=target_ref,
    )
    state.conditions.append(paralyzed)

    assert state._automatic_save_failure_provider_ids_for(
        target_ref,
        "strength",
    ) == (paralyzed.id,)
    assert state._automatic_save_failure_provider_ids_for(
        target_ref,
        "dexterity",
    ) == (paralyzed.id,)
    assert state._automatic_save_failure_provider_ids_for(
        target_ref,
        "wisdom",
    ) == ()
    save = resolve_saving_throw(
        state.creatures[target_ref].creature,
        "dexterity",
        1,
        roller=lambda _sides: 20,
        automatic_failure_reasons=(paralyzed.id,),
    )
    assert save.check.success is False
    assert save.automatic_failure_reasons == (paralyzed.id,)


def test_stunned_target_grants_advantage_without_automatic_critical_hits() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    attacker_ref = state.current_decision().creature_ref
    target_ref = "goblin_1"
    state.creatures[target_ref].position.x = state.active_position.x + 1
    state.creatures[target_ref].position.y = state.active_position.y
    stunned = build_applied_condition(
        condition=Condition.STUNNED,
        source_ref=attacker_ref,
        source_label=state._creature_label(attacker_ref),
        target_ref=target_ref,
    )
    state.conditions.append(stunned)

    mode = state._attack_roll_mode_for(
        attacker_ref,
        target_ref,
        "melee",
        state.active_position,
        (state.creatures[target_ref].position,),
    )

    assert mode == "advantage"
    assert state._automatic_critical_provider_ids_for(
        attacker_ref,
        target_ref,
    ) == ()
    assert state._automatic_save_failure_provider_ids_for(
        target_ref,
        "strength",
    ) == (stunned.id,)
    assert state._automatic_save_failure_provider_ids_for(
        target_ref,
        "dexterity",
    ) == (stunned.id,)


def test_stunned_creature_automatically_fails_dexterity_save() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    target_ref = "goblin_1"
    stunned = build_applied_condition(
        condition=Condition.STUNNED,
        source_ref="player",
        source_label="Traveler",
        target_ref=target_ref,
    )
    state.conditions.append(stunned)
    target = state._spell_target_context(
        state.creatures["player"].creature,
        target_ref,
    )
    assert target is not None

    save = resolve_saving_throw(
        target.creature,
        "dexterity",
        1,
        roller=lambda _sides: 20,
        automatic_failure_reasons=target.automatic_failure_reasons(
            "dexterity"
        ),
    )

    assert save.check.roll.selected == 20
    assert save.check.roll.total >= save.check.target
    assert save.check.success is False
    assert save.automatic_failure_reasons == (stunned.id,)


def test_action_target_requirement_uses_effective_conditions() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    actor_ref = state.current_decision().creature_ref
    target_ref = "goblin_1"
    actor = state.creatures[actor_ref].creature
    actor.stat_block_actions["Extract Brain"] = AttackActionDefinition(
        name="Extract Brain",
        attack_modes=("melee",),
        attack_bonus=0,
        target=ActionTarget(
            kind="creature",
            range_feet=5,
            requirements=(
                ConditionRequirement(
                    conditions=("incapacitated",),
                ),
            ),
        ),
        reach_feet=5,
        range_normal_feet=None,
        range_long_feet=None,
        hit=(),
    )
    action = EncounterAction(
        "Extract Brain",
        "attack",
        target_ref,
        id="extract-brain",
        creature_ref=actor_ref,
        preferred_attack_name="Extract Brain",
        cost=ActionCost(action=1),
    )
    assert any(
        failure.code == "target_condition_required"
        for failure in state.action_eligibility(action).failures
    )
    state.conditions.append(
        build_applied_condition(
            condition=Condition.PARALYZED,
            source_ref=actor_ref,
            source_label=actor.name,
            target_ref=target_ref,
        )
    )

    eligibility = state.action_eligibility(action)

    assert all(
        failure.code != "target_condition_required"
        for failure in eligibility.failures
    )


def test_conditions_showcase_is_externally_controlled_and_uses_immunities() -> None:
    session = Scenario(str(CONDITIONS_SHOWCASE_SCENARIO_DIR)).create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    assert all(
        state._creature_controller(creature_ref) == "external"
        for creature_ref in state.creatures
    )
    assert Condition.POISONED in (
        state.creatures["animated_armor"]
        .creature.statistics.condition_immunities
    )
    assert Condition.GRAPPLED in (
        state.creatures["air_elemental"]
        .creature.statistics.condition_immunities
    )
    assert state.creatures["assassin"].creature.multiattack is not None
    mage = state.creatures["condition_mage"].creature
    assert mage.spellcasting is not None
    assert {spell.id for spell in mage.spellcasting.learned_spells} == {
        "hold_person",
        "lesser_restoration",
    }
    hold_person = next(
        spell for spell in mage.spellcasting.learned_spells if spell.id == "hold_person"
    )
    assert hold_person.target_requirements == (
        CreatureTypeRequirement(("humanoid",)),
    )


def test_creature_type_restricted_spell_targets_are_visible_but_unavailable() -> None:
    session = Scenario(str(CONDITIONS_SHOWCASE_SCENARIO_DIR)).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    candidates = state._creature_action_candidates("condition_mage")
    hold_person_actions = [
        action
        for action in candidates
        if action.kind == "spell" and str(action.value).startswith("hold_person:")
    ]

    by_target = {
        str(action.value).split(":")[1]: state.action_eligibility(action)
        for action in hold_person_actions
    }

    assert by_target["veteran"].allowed
    assert not by_target["animated_armor"].allowed
    assert by_target["animated_armor"].failures[0].code == (
        "target_creature_type_required"
    )


def test_execution_rechecks_action_eligibility() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    move = next(action for action in state.available_actions() if action.kind == "move" and action.value == "right")
    actor = state.creatures[state.current_decision().creature_ref]
    blocker = state.creatures["goblin_1"]
    blocker.position = Position(actor.position.x + 1, actor.position.y)

    with pytest.raises(ValueError, match="destination is not free"):
        state.apply_action(move)


def test_cli_encounter_renderer_generates_grid_text() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None

    scene_text = render_encounter_text(session.encounter_state)

    assert "A" in scene_text
    assert "E" in scene_text
    assert "Round 1 - Turn: Traveler (player)" in scene_text
    assert "Movement remaining: 6/6 squares" in scene_text
    assert "Actor HP:" in scene_text


def test_movement_preview_uses_shortest_paths_around_occupied_cells() -> None:
    unobstructed_paths = GameWindow._shortest_movement_paths(
        width=4,
        height=4,
        origin=(0, 0),
        blocked=set(),
        max_steps=2,
    )
    movement_paths = GameWindow._shortest_movement_paths(
        width=4,
        height=4,
        origin=(0, 0),
        blocked={(1, 0)},
        max_steps=2,
    )

    assert unobstructed_paths[(2, 1)] == ("right", "down-right")
    assert movement_paths[(2, 0)] == ("down-right", "up-right")
    assert (1, 0) not in movement_paths
    assert (3, 3) not in movement_paths


def test_initiative_is_rolled_for_all_combatants_at_encounter_start(
    monkeypatch,
) -> None:
    monkeypatch.setattr(EncounterState, "_roll_initiative", _ROLL_INITIATIVE)
    rolls = iter([12, 18, 7, 14])
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls))
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    session.get_scene_view()

    assert session.encounter_state is not None
    assert [entry.creature_ref for entry in session.encounter_state.initiative_entries] == [
        "goblin_1",
        "goblin_3",
        "player",
        "goblin_2",
    ]
    assert [entry.total for entry in session.encounter_state.initiative_entries] == [
        20,
        16,
        13,
        9,
    ]
    assert session.encounter_state.current_decision().creature_ref == "goblin_1"


def test_presentation_exposes_initiative_tracker(monkeypatch) -> None:
    monkeypatch.setattr(EncounterState, "_roll_initiative", _ROLL_INITIATIVE)
    rolls = iter([12, 18, 7, 14])
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls))
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert [creature.token_image for creature in presentation.encounter.battlefield.creatures] == [
        "tokens/traveler.png",
        "tokens/goblin.png",
        "tokens/goblin.png",
        "tokens/goblin.png",
    ]
    assert [creature.team_color for creature in presentation.encounter.battlefield.creatures] == [
        "#3f7fd5",
        "#d64545",
        "#d64545",
        "#d64545",
    ]
    assert [(entry.name, entry.total, entry.is_active) for entry in presentation.encounter.resources.initiative] == [
        ("Goblin Warrior", 20, True),
        ("Goblin Warrior", 16, False),
        ("Traveler", 13, False),
        ("Goblin Warrior", 9, False),
    ]


def test_goblin_encounter_movement_consumes_movement_before_turn_advances() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    move_up_index = _action_id_by_label(session, "Move up")
    result = session.choose(move_up_index)

    assert ("system", "Traveler moves up to (1, 5).") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.active_position.x == 1
    assert session.encounter_state.active_position.y == 5
    assert session.encounter_state.active_movement_remaining == 5
    assert session.encounter_state.creatures["goblin_1"].position.x == 5
    assert session.encounter_state.creatures["goblin_1"].position.y == 2
    assert session.encounter_state.creatures["goblin_2"].position.x == 6
    assert session.encounter_state.creatures["goblin_2"].position.y == 2
    assert session.encounter_state.creatures["goblin_3"].position.x == 4
    assert session.encounter_state.creatures["goblin_3"].position.y == 1
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 1


def test_goblin_encounter_allows_diagonal_movement() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    move_index = _action_id_by_label(session, "Move up-right")
    result = session.choose(move_index)

    assert ("system", "Traveler moves up-right to (2, 5).") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.active_position.x == 2
    assert session.encounter_state.active_position.y == 5


def test_action_must_belong_to_current_decision_actor() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    action = next(action for action in session.encounter_state.available_actions() if action.kind == "move")
    action.creature_ref = "goblin_1"

    with pytest.raises(
        ValueError,
        match="not current decision actor 'player'",
    ):
        session.choose_encounter_action(action)


def test_enriched_multiattack_queues_named_attacks(monkeypatch) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    elemental = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "air-elemental",
                "stat_block": {"name": "Air Elemental", "source": "XMM"},
            }
        ),
        bestiary=load_bestiary_catalog(SYSTEM_CONTENT_ROOT),
    )
    state.active_creature_state.creature = elemental
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )

    multiattack = next(action for action in state.available_actions() if action.kind == "multiattack")
    initial_actions = state.available_actions()
    assert multiattack.value is None
    assert any(action.kind == "attack" for action in initial_actions)

    started = state.apply_action(multiattack)

    assert state.active_creature_state.actions_remaining == 0
    assert state.active_creature_state.attacks_remaining == 2
    assert [slot.options[0].name for slot in state.active_creature_state.pending_multiattack] == [
        "Thunderous Slam",
        "Thunderous Slam",
    ]
    assert not any(event.type == "attack_resolved" for event in started.events)

    invocation = next(
        action for action in state.available_actions() if action.kind == "attack" and action.value == "goblin_1"
    )
    assert invocation.source_trigger_id == "Thunderous Slam"
    first = state.apply_action(invocation)

    assert state.active_creature_state.attacks_remaining == 1
    assert [slot.options[0].name for slot in state.active_creature_state.pending_multiattack] == ["Thunderous Slam"]
    assert [event.data["attack_name"] for event in first.events if event.type == "attack_resolved"] == [
        "Thunderous Slam"
    ]

    second_invocation = next(
        action for action in state.available_actions() if action.kind == "attack" and action.value == "goblin_1"
    )
    second = state.apply_action(second_invocation)

    assert state.active_creature_state.attacks_remaining == 0
    assert state.active_creature_state.pending_multiattack == []
    assert [event.data["attack_name"] for event in second.events if event.type == "attack_resolved"] == [
        "Thunderous Slam"
    ]


def test_assassin_multiattack_applies_independent_poisoned_conditions(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    assassin = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "assassin",
                "stat_block": {"name": "Assassin", "source": "XMM"},
            }
        ),
        bestiary=load_bestiary_catalog(SYSTEM_CONTENT_ROOT),
    )
    state.active_creature_state.creature = assassin
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_1"].creature.current_health = 100
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 20,
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda count, _sides: count,
    )

    multiattack = next(
        action
        for action in state.available_actions()
        if action.kind == "multiattack"
    )
    assert state.action_eligibility(multiattack).allowed is True
    state.apply_action(multiattack)

    for _ in range(3):
        shortsword = next(
            action
            for action in state.available_actions()
            if action.kind == "attack"
            and action.value == "goblin_1"
            and action.preferred_attack_name == "Shortsword"
        )
        state.apply_action(shortsword)

    poisoned = [
        condition
        for condition in state.conditions_for("goblin_1")
        if condition.condition is Condition.POISONED
    ]
    assert len(poisoned) == 3
    assert len({condition.id for condition in poisoned}) == 3
    assert all(condition.source_ref == "player" for condition in poisoned)
    assert all(
        condition.duration == UntilTurnStart("player", 2)
        for condition in poisoned
    )

    state.turn_engine.expire_conditions_for_turn_start(state, "player", 1)
    assert state.has_condition("goblin_1", Condition.POISONED) is True

    state.round.number = 2
    state.turn_engine.expire_conditions_for_turn_start(state, "player", 2)
    assert state.has_condition("goblin_1", Condition.POISONED) is False


def test_multiattack_showcase_loads_enriched_creatures() -> None:
    scenario = Scenario(MULTIATTACK_SCENARIO_DIR)
    session = scenario.create_session()
    session.get_scene_view()

    assert scenario.display_name == "Multiattack Showcase"
    assert session.encounter_state is not None
    creatures = {state.creature.id: state.creature for state in session.encounter_state.creatures.values()}
    assert set(creatures) == {"player", "air_elemental", "aboleth"}
    assert creatures["player"].multiattack is not None
    player_sequence = creatures["player"].multiattack.executable_sequence(
        {
            action.name
            for action in creatures["player"].stat_block_actions.values()
            if isinstance(action, AttackActionDefinition)
        }
    )
    assert [invocation.name for invocation in player_sequence] == [
        "Rend",
        "Rend",
        "Rend",
    ]
    assert creatures["air_elemental"].multiattack is not None
    elemental_sequence = creatures["air_elemental"].multiattack.executable_sequence(
        {
            action.name
            for action in creatures["air_elemental"].stat_block_actions.values()
            if isinstance(action, AttackActionDefinition)
        }
    )
    assert [invocation.name for invocation in elemental_sequence] == [
        "Thunderous Slam",
        "Thunderous Slam",
    ]
    assert creatures["aboleth"].multiattack is not None
    aboleth_sequence = creatures["aboleth"].multiattack.executable_sequence(
        {
            action.name
            for action in creatures["aboleth"].stat_block_actions.values()
            if isinstance(action, AttackActionDefinition)
        }
    )
    assert [invocation.name for invocation in aboleth_sequence] == [
        "Tentacle",
        "Tentacle",
    ]
    assert creatures["player"].attributes.movement.speed_feet == 40
    assert creatures["air_elemental"].attributes.movement.speed_feet == 10
    assert creatures["aboleth"].attributes.movement.speed_feet == 10
    runtime_creatures = session.encounter_state.export_state()["creatures"]
    assert runtime_creatures["player"]["movement_total_feet"] == 80
    assert runtime_creatures["air_elemental"]["movement_total_feet"] == 90
    assert runtime_creatures["aboleth"]["movement_total_feet"] == 10
    assert {creature["controller"] for creature in runtime_creatures.values()} == {"external"}


def test_aboleth_tentacle_grapples_and_exposes_fixed_dc_escape(
    monkeypatch,
) -> None:
    session = Scenario(MULTIATTACK_SCENARIO_DIR).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.creatures["air_elemental"].creature.statistics = replace(
        state.creatures["air_elemental"].creature.statistics,
        condition_immunities=frozenset(),
    )
    state.initiative_order = ["aboleth", "air_elemental", "player"]
    state.turn_index = 0
    state.creatures["aboleth"].position.x = 7
    state.creatures["aboleth"].position.y = 4
    state.creatures["air_elemental"].position.x = 5
    state.creatures["air_elemental"].position.y = 4
    state.creatures["player"].position.x = 4
    state.creatures["player"].position.y = 4
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 20,
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda count, _sides: count,
    )

    multiattack = next(action for action in state.available_actions() if action.kind == "multiattack")
    state.apply_action(multiattack)
    tentacle = next(
        action for action in state.available_actions() if action.kind == "attack" and action.value == "air_elemental"
    )
    state.apply_action(tentacle)

    grapple = next(
        condition
        for condition in state.conditions_for("air_elemental")
        if condition.condition is Condition.GRAPPLED
    )
    assert grapple.source_ref == "aboleth"
    assert grapple.metadata["escape_dc"] == 14
    assert state._grappling_targets_for("aboleth") == ("air_elemental",)
    assert state.export_state()["relationships"][0]["kind"] == "grappling"

    huge_target_tentacle = next(
        action for action in state.available_actions() if action.kind == "attack" and action.value == "player"
    )
    state.apply_action(huge_target_tentacle)
    assert state.has_condition("player", Condition.GRAPPLED) is False

    state.initiative_order = ["air_elemental", "aboleth", "player"]
    state.turn_index = 0
    state.creatures["air_elemental"].actions_remaining = 1
    failed_escape = next(action for action in state.available_actions() if action.kind == "escape_grapple")
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )
    failed = state.apply_action(failed_escape)
    assert state.has_condition("air_elemental", Condition.GRAPPLED) is True
    assert state.creatures["air_elemental"].actions_remaining == 0
    assert any("fails to escape" in text for _, text in failed.messages)

    state.creatures["air_elemental"].actions_remaining = 1
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 20,
    )
    escape = next(action for action in state.available_actions() if action.kind == "escape_grapple")
    result = state.apply_action(escape)

    assert escape.label == "Escape The Deep One (DC 14)"
    assert state.has_condition("air_elemental", Condition.GRAPPLED) is False
    assert state._grappling_targets_for("aboleth") == ()
    assert any("escapes The Deep One's grapple" in text for _, text in result.messages)


def test_tentacle_grapple_enforces_capacity_without_counting_duplicates() -> None:
    session = Scenario(MULTIATTACK_SCENARIO_DIR).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    aboleth_ref = "aboleth"
    template = state.creatures["air_elemental"]
    template.creature.statistics = replace(
        template.creature.statistics,
        condition_immunities=frozenset(),
    )
    for index in range(4):
        state.creatures[f"tentacle-target:{index}"] = deepcopy(template)
    tentacle = state.creatures[aboleth_ref].creature.stat_block_actions["Tentacle"]
    assert isinstance(tentacle, AttackActionDefinition)
    [_, grapple_effect] = tentacle.hit

    for target_ref in (
        "air_elemental",
        "air_elemental",
        "tentacle-target:0",
        "tentacle-target:1",
        "tentacle-target:2",
        "tentacle-target:3",
    ):
        apply_attack_hit_effects(
            state,
            attacker_ref=aboleth_ref,
            target_ref=target_ref,
            effects=(grapple_effect,),
            progress=EncounterProgress(),
        )

    assert set(state._grappling_targets_for(aboleth_ref)) == {
        "air_elemental",
        "tentacle-target:0",
        "tentacle-target:1",
        "tentacle-target:2",
    }
    assert state.has_condition("tentacle-target:3", Condition.GRAPPLED) is False


def test_fallback_tokens_use_team_colors() -> None:
    blue_fill, blue_border = BattlefieldWidget._fallback_token_colors("#3f7fd5")
    red_fill, red_border = BattlefieldWidget._fallback_token_colors("#d64545")

    assert blue_fill.name() == "#3f7fd5"
    assert red_fill.name() == "#d64545"
    assert blue_border.name() != red_border.name()


def test_grappled_blocks_movement_and_disadvantages_attacks() -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 6
    state.creatures["goblin_2"].position.y = 2
    state.creatures["goblin_3"].position.x = 1
    state.creatures["goblin_3"].position.y = 1
    state._apply_grapple(
        condition_from_effect(
            EffectResult(
                kind="apply_condition",
                target_ref="player",
                data={
                    "condition": "grappled",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            )
        )
    )

    labels = _action_labels(session)
    assert not any(label.startswith("Move ") for label in labels)
    assert (
        state._attack_roll_mode_for(
            "player",
            "goblin_2",
            "melee",
            state.active_position,
            tuple(
                creature_state.position
                for creature_ref, creature_state in state.creatures.items()
                if creature_ref != state.current_decision().creature_ref and creature_state.is_alive
            ),
        )
        == "disadvantage"
    )
    assert (
        state._attack_roll_mode_for(
            "player",
            "goblin_1",
            "melee",
            state.active_position,
            tuple(
                creature_state.position
                for creature_ref, creature_state in state.creatures.items()
                if creature_ref != state.current_decision().creature_ref and creature_state.is_alive
            ),
        )
        == "normal"
    )


def test_grapple_action_is_available_in_the_combat_menu(monkeypatch) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3

    rolls = iter([20, 1])
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls))

    scene_view = session.get_scene_view()
    grapple_index = _action_id(session, "grapple", "goblin_1")
    result = session.choose(grapple_index)

    assert (
        "system",
        "Traveler grapples Goblin Warrior (goblin_1).",
    ) in result.messages
    assert session.encounter_state.has_condition("goblin_1", Condition.GRAPPLED) is True
    assert session.encounter_state._grappling_targets_for("player") == ("goblin_1",)
    assert any(action.kind == "grapple" and action.value == "goblin_1" for action in scene_view.action_details)


def test_grapple_replaces_only_one_attack_in_multiattack(monkeypatch) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    session.decision_creature.combat_profile.attacks_per_attack_action = 2
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 10,
    )

    session.choose(_action_id(session, "grapple", "goblin_1"))

    assert state.active_action_available is False
    assert state.active_attacks_remaining == 1
    assert any(action.kind == "attack" for action in state.available_actions())


def test_grapple_can_replace_remaining_attack_after_weapon_attack(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    session.decision_creature.combat_profile.attacks_per_attack_action = 2
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_1"].creature.current_health = 20
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )

    session.choose(_action_id(session, "attack", "goblin_1"))
    assert state.active_attacks_remaining == 1

    session.choose(_action_id(session, "grapple", "goblin_1"))

    assert state.active_attacks_remaining == 0
    assert not any(action.kind in {"attack", "grapple"} for action in state.available_actions())


def test_grappling_moves_target_and_costs_extra_movement() -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 6
    state.creatures["goblin_2"].position.y = 2
    state.creatures["goblin_3"].position.x = 1
    state.creatures["goblin_3"].position.y = 1
    state._apply_grapple(
        condition_from_effect(
            EffectResult(
                kind="apply_condition",
                target_ref="goblin_1",
                data={
                    "condition": "grappled",
                    "source_ref": "player",
                    "source_label": "Traveler",
                },
            )
        )
    )

    move_up_index = _action_id_by_label(session, "Move up")
    result = session.choose(move_up_index)

    assert ("system", "Traveler moves up to (4, 3).") in result.messages
    assert state.active_position.x == 4
    assert state.active_position.y == 3
    assert state.creatures["goblin_1"].position.x == 4
    assert state.creatures["goblin_1"].position.y == 2
    assert state.creatures["goblin_1"].reaction_available is True
    assert not any(event.type == "opportunity_attack_resolved" for event in result.events)
    assert state.active_movement_remaining == 4


def test_spending_last_movement_square_does_not_auto_end_turn() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    for _ in range(6):
        move_right_index = _action_id_by_label(session, "Move right")
        result = session.choose(move_right_index)

    assert ("system", "Traveler moves right to (7, 6).") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 1
    assert _action_labels(session).count("Wait") == 1


def test_goblin_encounter_wait_advances_enemy_turns() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    move_up_index = _action_id_by_label(session, "Move up")
    session.choose(move_up_index)
    wait_index = _action_id_by_label(session, "Wait")
    result = session.choose(wait_index)

    assert ("system", "Traveler waits.") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.creatures["goblin_1"].position.x == 2
    assert session.encounter_state.creatures["goblin_1"].position.y == 5
    assert session.encounter_state.creatures["goblin_2"].position.x == 3
    assert session.encounter_state.creatures["goblin_2"].position.y == 5
    assert session.encounter_state.creatures["goblin_3"].position.x == 4
    assert session.encounter_state.creatures["goblin_3"].position.y == 1
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 2


def test_color_spray_appears_as_spell_action_when_enemy_is_in_range() -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    session.encounter_state.creatures["goblin_1"].creature.current_health = 30
    session.encounter_state.creatures["goblin_1"].creature.current_health = 30

    assert "Cast Color Spray" in _action_labels(session)


def test_burning_hands_appears_as_spell_action_when_enemy_is_in_range() -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2

    assert "Cast Burning Hands" in _action_labels(session)
    assert "Cast Burning Hands (Level 2)" in _action_labels(session)
    assert "Cast Burning Hands (Level 3)" in _action_labels(session)


def test_presentation_derives_spell_slot_rows_from_player_spellcasting(
    monkeypatch,
) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5)

    _choose_directional_spell(session, "Cast Color Spray", (4, 2))
    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert presentation.encounter.resources.spell_slots == (
        SpellSlotTrackView(level=1, remaining=3, maximum=4),
        SpellSlotTrackView(level=2, remaining=3, maximum=3),
        SpellSlotTrackView(level=3, remaining=2, maximum=2),
    )


def test_lesser_restoration_appears_when_player_has_removable_condition() -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.decision_creature.spellcasting is not None
    session.decision_creature.spellcasting.spell_slots_max[2] = 1
    session.decision_creature.spellcasting.spell_slots_remaining[2] = 1
    session.encounter_state._apply_effects(
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
        ]
    )

    assert any(
        label.startswith("Cast Lesser Restoration")
        for label in _action_labels(session)
    )


def test_color_spray_consumes_slot_and_applies_blinded_on_failed_save(
    monkeypatch,
) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.decision_creature.spellcasting is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 2))

    assert ("system", "Traveler casts Color Spray.") in result.messages
    assert any("Color Spray affects Goblin Warrior." == message for _, message in result.messages)
    assert session.encounter_state.active_action_available is False
    assert session.decision_creature.spellcasting.spell_slots_remaining[1] == 3
    assert session.encounter_state.has_condition("goblin_1", Condition.BLINDED) is True
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Color Spray"
    assert spell_event.data["save_detail"]["ability"] == "constitution"
    assert spell_event.data["save_detail"]["success"] is False
    assert spell_event.data["effects"][0]["data"]["condition"] == "blinded"


def test_color_spray_cone_can_affect_multiple_enemies(monkeypatch) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.decision_creature.spellcasting is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 4
    state.creatures["goblin_2"].position.y = 2
    state.creatures["goblin_3"].creature.current_health = 0

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))

    assert state.has_condition("goblin_1", Condition.BLINDED) is True
    assert state.has_condition("goblin_2", Condition.BLINDED) is True
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["target_refs"] == ["goblin_1", "goblin_2"]
    assert spell_event.data["area"]["shape"] == "cone"
    assert spell_event.data["area"]["origin"] == {"x": 4, "y": 4}
    assert spell_event.data["area"]["rasterization_policy"] == "coverage_threshold"
    assert spell_event.data["area"]["coverage_threshold"] == 0.1
    assert len(spell_event.data["save_details"]) == 2
    assert [effect["target_ref"] for effect in spell_event.data["effects"]] == [
        "goblin_1",
        "goblin_2",
    ]


def test_color_spray_cone_uses_continuous_aim_vector(monkeypatch) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 5
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 5
    state.creatures["goblin_2"].position.y = 4
    state.creatures["goblin_3"].creature.current_health = 0

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (5, 3))

    assert state.has_condition("goblin_1", Condition.BLINDED) is True
    assert state.has_condition("goblin_2", Condition.BLINDED) is True
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["target_refs"] == ["goblin_1", "goblin_2"]
    assert spell_event.data["area"]["continuous_area"]["direction"] == {
        "x": 0.9486832980505138,
        "y": -0.31622776601683794,
    }


def test_burning_hands_cone_damages_multiple_enemies(monkeypatch) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

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
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: next(rolls))

    result = _choose_directional_spell(session, "Cast Burning Hands", (4, 3))

    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Burning Hands"
    assert spell_event.data["save_details"][0]["ability"] == "dexterity"
    assert spell_event.data["damage_roll_details"][0]["dice"] == "3d6"
    assert spell_event.data["damage_roll_details"][0]["applied_damage"] == 8
    assert spell_event.data["damage_roll_details"][1]["applied_damage"] == 4
    assert spell_event.data["damage_roll_details"][0]["dice_values"] == [5, 1, 2]
    assert spell_event.data["damage_roll_details"][1]["dice_values"] == [5, 1, 2]
    assert state.creatures["goblin_1"].creature.get_health() == 2
    assert state.creatures["goblin_2"].creature.get_health() == 6
    assert sum("Burning Hands damages" in message for _, message in result.messages) == 2
    assert not any("Enemy 2 (Goblin Warrior) is defeated." == message for _, message in result.messages)


def test_burning_hands_can_use_and_scale_a_higher_level_slot(monkeypatch) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )

    result = _choose_directional_spell(
        session, "Cast Burning Hands (Level 3)", (4, 3)
    )

    event = next(event for event in result.events if event.type == "spell_cast")
    assert event.data["slot_level"] == 3
    assert event.data["damage_roll_detail"]["dice"] == "5d6"
    assert event.data["spell_slots_remaining"] == 1


def test_fireball_point_area_damages_multiple_enemies(monkeypatch) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.decision_creature.spellcasting is not None
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
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls))

    result = _choose_directional_spell(session, "Cast Fireball", (5, 2))

    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Fireball"
    assert spell_event.data["target_refs"] == ["goblin_1", "goblin_2", "goblin_3"]
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
    assert session.decision_creature.spellcasting.spell_slots_remaining[3] == 1
    assert state.creatures["goblin_1"].creature.get_health() == 0
    assert state.creatures["goblin_2"].creature.get_health() == 0
    assert state.creatures["goblin_3"].creature.get_health() == 0


def test_pyside6_window_extracts_spell_area_overlay(monkeypatch) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 4
    state.creatures["goblin_2"].position.y = 2
    state.creatures["goblin_3"].creature.current_health = 0

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))
    area = next(event.data["area"] for event in result.events if event.type == "spell_cast")

    assert area is not None
    assert area["shape"] == "cone"
    assert area["origin"] == {"x": 4, "y": 4}
    assert area["rasterization_policy"] == "coverage_threshold"
    assert area["coverage_threshold"] == 0.1
    assert len(area["cells"]) >= 2


def test_pyside6_window_does_not_keep_spell_overlay_after_cast(monkeypatch) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5)
    monkeypatch.setattr(
        "srd_arena.frontends.qt.app.QTimer",
        SimpleNamespace(singleShot=lambda _delay, callback: callback()),
    )

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))

    window = GameWindow.__new__(GameWindow)
    window.session = session
    window._presentation = SimpleNamespace(encounter=object())
    window._combat_log_scene_id = state.encounter_id
    window.dice_roll_panel = SimpleNamespace(
        append_entry=lambda _messages, _rolls: None,
    )
    window._scroll_roll_log_to_bottom = lambda: None
    window.refresh_view = lambda: None
    window.close = lambda: None

    GameWindow._apply_turn_result(window, result)

    assert not hasattr(window, "_resolved_area_overlay")


def test_battlefield_widget_preview_overlay_reaims_directional_area(
    monkeypatch,
) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 4
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 3
    state.creatures["goblin_2"].position.x = 4
    state.creatures["goblin_2"].position.y = 2
    state.creatures["goblin_3"].creature.current_health = 0

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5)

    result = _choose_directional_spell(session, "Cast Color Spray", (4, 3))
    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    original_area = next(event.data["area"] for event in result.events if event.type == "spell_cast")
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
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.decision_creature.spellcasting is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 2
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    rolls = iter([5, 17, 4, 1])
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: next(rolls, 3))
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 1)

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))
    result = session.choose(_action_id_by_label(session, "Wait"))

    attack_event = next(
        event for event in result.events if event.type == "attack_resolved" and event.creature_ref == "goblin_1"
    )
    assert attack_event.data["attack_roll_detail"]["mode"] == "disadvantage"
    assert attack_event.data["attack_roll_detail"]["dice"] == [17, 4]


def test_attacks_against_blinded_target_gain_advantage(monkeypatch) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 2
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5)

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))

    attack_mode = state._attack_roll_mode_for(
        "player",
        "goblin_1",
        "melee",
        state.active_position,
        (state.creatures["goblin_1"].position,),
    )

    assert attack_mode == "advantage"


def test_blinded_from_color_spray_expires_at_end_of_players_next_turn(
    monkeypatch,
) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 2
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    rolls = iter([5, 3, 3])
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: next(rolls, 3))
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 1)

    _choose_directional_spell(session, "Cast Color Spray", (3, 2))
    session.choose(_action_id_by_label(session, "Wait"))

    assert state.has_condition("goblin_1", Condition.BLINDED) is True

    session.choose(_action_id_by_label(session, "Wait"))

    assert state.has_condition("goblin_1", Condition.BLINDED) is False


def test_reapplying_blinded_preserves_independent_durations(monkeypatch) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 1
    state.active_position.y = 1
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 1
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5)
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 1)

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
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 2
    state.active_position.y = 2
    state.creatures["goblin_1"].position.x = 3
    state.creatures["goblin_1"].position.y = 2

    state._apply_effects(
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
        ]
    )
    assert state.has_condition("goblin_1", Condition.BLINDED) is True
    assert (
        state._attack_roll_mode_for(
            "player",
            "goblin_1",
            "melee",
            state.active_position,
            (state.creatures["goblin_1"].position,),
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
                kind="remove_condition",
                target_ref="goblin_1",
                data={"condition": "blinded"},
            ),
        ]
    )

    assert messages == [("system", "Status removed.")]
    assert state.has_condition("goblin_1", Condition.BLINDED) is False
    assert (
        state._attack_roll_mode_for(
            "player",
            "goblin_1",
            "melee",
            state.active_position,
            (state.creatures["goblin_1"].position,),
        )
        == "normal"
    )


def test_lesser_restoration_consumes_bonus_action_and_removes_condition() -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    assert session.decision_creature.spellcasting is not None
    session.decision_creature.spellcasting.spell_slots_max[2] = 1
    session.decision_creature.spellcasting.spell_slots_remaining[2] = 1
    state = session.encounter_state
    state._apply_effects(
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
        ]
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
    assert session.decision_creature.spellcasting.spell_slots_remaining[2] == 0
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Lesser Restoration"
    assert spell_event.data["target_ref"] == "player"
    assert spell_event.data["success"] is True
    assert spell_event.data["effects"][0]["kind"] == "remove_condition"


def test_cure_wounds_heals_through_generic_spell_resolution(monkeypatch) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Cure Wounds", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[1] = 1
    caster.current_health = caster.get_max_health() - 12
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: 4
    )

    result = session.choose(_action_id_by_prefix(session, "Cast Cure Wounds"))

    assert caster.get_health() == caster.get_max_health() - 3
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["success"] is True
    assert spell_event.data["healing_roll_detail"]["total"] == 9
    assert spell_event.data["healing_roll_detail"]["applied"] == 9


def test_false_life_grants_scaled_temporary_hit_points(monkeypatch) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("False Life", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: 3
    )

    result = session.choose(
        _action_id_by_prefix(session, "Cast False Life (Level 2)")
    )

    assert caster.temporary_hit_points == 15
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["temporary_hit_point_detail"]["total"] == 15
    assert spell_event.data["temporary_hit_point_detail"]["applied"] == 15


def test_mass_healing_word_uses_one_roll_for_selected_targets(monkeypatch) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell(
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
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: 3
    )

    initial = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value) == "mass_healing_word:goblin_1"
    )
    state.apply_action(initial)
    add_second = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target"
        and action.value == "goblin_2"
    )
    state.apply_action(add_second)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )

    result = state.apply_action(confirm)

    event = next(event for event in result.events if event.type == "spell_cast")
    details = event.data["healing_roll_details"]
    assert [detail["target_ref"] for detail in details] == ["goblin_1", "goblin_2"]
    assert details[0]["dice_values"] == details[1]["dice_values"] == [3, 3]
    assert all(detail["applied"] == 7 for detail in details)


def test_heal_upcasts_and_removes_every_listed_condition() -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Heal", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[7] = 1
    caster.max_health_override = 200
    caster.current_health = 50
    for condition in ("blinded", "poisoned"):
        state._apply_effects(
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
            ]
        )

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("heal:player")
        and parse_spell_action_slot(str(action.value)) == 7
    )
    result = state.apply_action(action)

    assert caster.get_health() == 130
    assert state.has_condition("player", Condition.BLINDED) is False
    assert state.has_condition("player", Condition.POISONED) is False
    event = next(event for event in result.events if event.type == "spell_cast")
    assert event.data["healing_roll_detail"]["total"] == 80
    assert [effect["data"]["condition"] for effect in event.data["effects"]] == [
        "blinded",
        "poisoned",
    ]


def test_aid_upcasts_for_multiple_targets_and_reverts_on_expiry() -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Aid", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[3] = 1
    target = state.creatures["goblin_1"]
    target.position = Position(state.active_position.x + 1, state.active_position.y)
    original = {
        "player": (caster.get_max_health(), caster.get_health()),
        "goblin_1": (
            target.creature.get_max_health(),
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
    state.apply_action(initial)
    add_target = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target"
        and action.value == "goblin_1"
    )
    state.apply_action(add_target)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    state.apply_action(confirm)

    assert caster.get_max_health() == original["player"][0] + 10
    assert caster.get_health() == original["player"][1] + 10
    assert target.creature.get_max_health() == original["goblin_1"][0] + 10
    assert target.creature.get_health() == original["goblin_1"][1] + 10

    state.round.number = 4801
    expire_ongoing_effects_for_turn_start(state, "player")

    assert (caster.get_max_health(), caster.get_health()) == original["player"]
    assert (
        target.creature.get_max_health(),
        target.creature.get_health(),
    ) == original["goblin_1"]


def test_mass_heal_uses_bounded_numeric_allocations() -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Mass Heal", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[9] = 1
    target = state.creatures["goblin_1"]
    target.position = Position(state.active_position.x + 1, state.active_position.y)
    caster.max_health_override = 500
    caster.current_health = 100
    target.creature.max_health_override = 500
    target.creature.current_health = 100
    state._apply_effects(
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
        ]
    )

    initial = next(
        action
        for action in state.available_actions()
        if action.kind == "spell" and str(action.value).startswith("mass_heal:")
    )
    opened = state.apply_action(initial)

    assert opened.paused_for_decision
    assert state.pending_spell_cast is not None
    assert state.pending_spell_cast.resource_pool_total == 700
    for target_ref, amount in (("player", 300), ("goblin_1", 400)):
        state.apply_action(
            EncounterAction(
                label="Set healing allocation",
                kind="set_spell_resource_allocation",
                value=f"{target_ref}~{amount}",
                id=f"player-spell-allocation-{target_ref}",
                creature_ref="player",
            )
        )
    with pytest.raises(ValueError, match="remaining healing pool"):
        state.apply_action(
            EncounterAction(
                label="Over-allocate healing",
                kind="set_spell_resource_allocation",
                value="player~301",
                id="player-spell-allocation-player",
                creature_ref="player",
            )
        )
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    result = state.apply_action(confirm)

    assert caster.get_health() == 400
    assert target.creature.get_health() == 500
    assert state.has_condition("goblin_1", Condition.BLINDED) is False
    event = next(event for event in result.events if event.type == "spell_cast")
    assert {
        detail["target_ref"]: detail["allocated"]
        for detail in event.data["healing_roll_details"]
    } == {"player": 300, "goblin_1": 400}


def test_greater_restoration_selects_a_specific_sourced_effect() -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell(
            "Greater Restoration", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[5] = 1
    state._apply_effects(
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
    state._apply_effects(
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
    result = state.apply_action(curse_action)

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
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Remove Curse", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[3] = 1
    for index in (1, 2):
        state._apply_effects(
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
    state.apply_action(action)

    assert not any(effect.kind.value == "curse" for effect in state.ongoing_effects)


def test_greater_restoration_removes_all_maximum_hit_point_reductions() -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell(
            "Greater Restoration", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[5] = 1
    original = (caster.get_max_health(), caster.get_health())
    state._apply_effects(
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
                    "parameters": {
                        "maximum_hit_point_modifier": -10,
                        "also_modify_current_hit_points": True,
                    },
                },
            )
        ],
        origin_id="withering-origin",
    )
    assert (caster.get_max_health(), caster.get_health()) == (
        original[0] - 10,
        original[1] - 10,
    )

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and "hit_point_maximum_reduction" in str(action.value)
    )
    state.apply_action(action)

    assert (caster.get_max_health(), caster.get_health()) == original


def test_lesser_restoration_uses_magic_menu_bucket() -> None:
    bucket = GameWindow._action_bucket_key(
        None,
        ActionView(
            id="spell-lesser-restoration-player",
            label="Cast Lesser Restoration",
            kind="spell",
            creature_ref="player",
            value="lesser_restoration:player",
            cost={"bonus_action": 1},
        ),
    )

    assert bucket == "magic"


def test_lesser_restoration_explicitly_selects_the_condition_to_remove() -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    assert session.decision_creature.spellcasting is not None
    session.decision_creature.spellcasting.spell_slots_remaining[2] = 1
    for condition in ("blinded", "poisoned"):
        state._apply_effects(
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
            ]
        )

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).endswith("#poisoned")
    )
    state.apply_action(action)

    assert state.has_condition("player", Condition.POISONED) is False
    assert state.has_condition("player", Condition.BLINDED) is True


def test_hold_person_applies_concentration_and_ends_after_repeated_save(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell(
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
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: next(rolls),
    )

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("hold_person:goblin_1")
    )
    cast = state.apply_action(action)

    assert state.has_condition("goblin_1", Condition.PARALYZED) is True
    assert state.effective_conditions_for("goblin_1").has(
        Condition.INCAPACITATED
    )
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
    state.turn_index = 1
    state.turn_engine.advance_turn(state, cast)

    assert state.has_condition("goblin_1", Condition.PARALYZED) is False
    assert state.ongoing_effects == []
    assert any("succeeds on the repeated Wisdom save" in text for _, text in cast.messages)


def test_one_target_repeat_save_does_not_end_multi_target_spell(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
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
                "parameters": {
                    "repeat_save_trigger": "end_of_turn",
                    "save_ability": "wisdom",
                    "save_dc": 10,
                },
            },
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
    state._apply_effects(effects, origin_id="multi-target-cast")
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: 20
    )

    resolve_end_turn_effects(state, "goblin_1")

    assert state.has_condition("goblin_1", Condition.PARALYZED) is False
    assert state.has_condition("goblin_2", Condition.PARALYZED) is True
    assert state.ongoing_effects[0].target_refs == ("goblin_2",)


def test_upcast_hold_person_stages_and_resolves_multiple_targets(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell(
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
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: 1
    )

    initial = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("hold_person:goblin_1")
        and parse_spell_action_slot(str(action.value)) == 3
    )
    opened = state.apply_action(initial)

    assert opened.paused_for_decision
    assert state.current_decision().kind == "spell_targets"
    assert caster.spellcasting.spell_slots_remaining[3] == 1
    assert not any(
        action.kind == "toggle_spell_target"
        and action.value == "goblin_3"
        for action in state.available_actions()
    )
    with pytest.raises(ValueError, match="creature types: humanoid"):
        state.apply_action(
            EncounterAction(
                "Add invalid target",
                "toggle_spell_target",
                "goblin_3",
                id="crafted-invalid-spell-target",
                creature_ref="player",
            )
        )
    add_second = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target"
        and action.value == "goblin_2"
    )
    state.apply_action(add_second)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    resolved = state.apply_action(confirm)

    assert resolved.paused_for_decision is False
    assert state.current_decision().kind == "turn"
    assert caster.spellcasting.spell_slots_remaining[3] == 0
    assert state.has_condition("goblin_1", Condition.PARALYZED)
    assert state.has_condition("goblin_2", Condition.PARALYZED)
    assert state.ongoing_effects[0].target_refs == ("goblin_1", "goblin_2")


def test_scorching_ray_allocates_repeated_targets_without_enumerating_combinations(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell(
            "Scorching Ray", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda sides: 10 if sides == 20 else 3,
    )

    initial = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value) == "scorching_ray:goblin_1"
    )
    opened = state.apply_action(initial)

    assert opened.paused_for_decision
    assert state.pending_spell_cast is not None
    assert state.pending_spell_cast.selected_target_refs == ["goblin_1"]
    assert not any(
        action.kind == "confirm_spell_targets"
        for action in state.available_actions()
    )

    for target_ref in ("goblin_1", "goblin_2"):
        add_ray = next(
            action
            for action in state.available_actions()
            if action.kind == "toggle_spell_target"
            and action.value == target_ref
            and action.id.endswith("-add")
        )
        state.apply_action(add_ray)

    assert state.pending_spell_cast is not None
    assert state.pending_spell_cast.selected_target_refs == [
        "goblin_1",
        "goblin_1",
        "goblin_2",
    ]

    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    resolved = state.apply_action(confirm)

    spell_event = next(
        event for event in resolved.events if event.type == "spell_cast"
    )
    assert spell_event.data["target_refs"] == [
        "goblin_1",
        "goblin_1",
        "goblin_2",
    ]
    assert len(spell_event.data["attack_roll_details"]) == 3
    assert [
        detail["projectile_index"]
        for detail in spell_event.data["attack_roll_details"]
    ] == [1, 2, 3]
    assert len(spell_event.data["damage_roll_details"]) == 3
    assert caster.spellcasting.spell_slots_remaining[2] == 0


def test_staged_spell_targeting_can_be_cancelled_without_spending_resources() -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell(
            "Scorching Ray", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    initial = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value) == "scorching_ray:goblin_1"
    )
    state.apply_action(initial)

    cancel = next(
        action
        for action in state.available_actions()
        if action.kind == "cancel_spell_targets"
    )
    state.apply_action(cancel)

    assert state.pending_spell_cast is None
    assert state.current_decision().kind == "turn"
    assert caster.spellcasting.spell_slots_remaining[2] == 1
    assert state.active_actions_remaining == 1


def test_ray_of_sickness_combines_scaled_damage_and_timed_condition(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Ray of Sickness", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda sides: 15 if sides == 20 else 2,
    )

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("ray_of_sickness:goblin_1")
        and parse_spell_action_slot(str(action.value)) == 2
    )
    resolved = state.apply_action(action)

    spell_event = next(event for event in resolved.events if event.type == "spell_cast")
    assert spell_event.data["damage_roll_detail"]["dice"] == "3d8"
    assert state.has_condition("goblin_1", Condition.POISONED)


def test_eldritch_blast_uses_caster_level_for_beam_allocation(monkeypatch) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.attributes = replace(caster.attributes, level=11)
    caster.spellcasting.learned_spells.append(
        build_spell("Eldritch Blast", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda sides: 20 if sides == 20 else 4,
    )

    initial = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value) == "eldritch_blast:goblin_1"
    )
    state.apply_action(initial)

    assert state.pending_spell_cast is not None
    assert state.pending_spell_cast.maximum_targets == 3
    for target_ref in ("goblin_1", "goblin_2"):
        add_beam = next(
            action
            for action in state.available_actions()
            if action.kind == "toggle_spell_target"
            and action.value == target_ref
            and action.id.endswith("-add")
        )
        state.apply_action(add_beam)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    resolved = state.apply_action(confirm)

    spell_event = next(event for event in resolved.events if event.type == "spell_cast")
    assert spell_event.data["target_refs"] == [
        "goblin_1",
        "goblin_1",
        "goblin_2",
    ]
    assert len(spell_event.data["attack_roll_details"]) == 3
    assert len(spell_event.data["damage_roll_details"]) == 3


def test_ice_knife_explodes_on_a_miss_and_scales_only_cold_damage(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Ice Knife", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[2] = 1
    state.active_position.x = 1
    state.active_position.y = 1
    state.creatures["goblin_1"].position = Position(5, 5)
    state.creatures["goblin_2"].position = Position(6, 5)
    state.creatures["goblin_3"].position = Position(10, 10)
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda sides: 1 if sides == 20 else 2,
    )

    ice_knife_actions = [
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("ice_knife")
    ]
    assert ice_knife_actions
    action = next(
        action
        for action in ice_knife_actions
        if str(action.value).startswith("ice_knife:goblin_1")
        and parse_spell_action_slot(str(action.value)) == 2
    )
    resolved = state.apply_action(action)

    spell_event = next(event for event in resolved.events if event.type == "spell_cast")
    primary = next(
        detail
        for detail in spell_event.data["damage_roll_details"]
        if detail["damage_type"] == "piercing"
    )
    cold = [
        detail
        for detail in spell_event.data["damage_roll_details"]
        if detail["damage_type"] == "cold"
    ]
    assert primary["dice"] == "1d10"
    assert primary["final_damage"] == 0
    assert {detail["target_ref"] for detail in cold} == {"goblin_1", "goblin_2"}
    assert all(detail["dice"] == "3d6" for detail in cold)


def test_weird_deals_damage_on_a_failed_repeat_save(monkeypatch) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Weird", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    caster.spellcasting.spell_slots_remaining[9] = 1
    state.active_position.x = 1
    state.active_position.y = 1
    target = state.creatures["goblin_1"]
    target.position = Position(8, 8)
    target.creature.current_health = 200
    state.creatures["goblin_2"].position = Position(15, 1)
    state.creatures["goblin_3"].position = Position(15, 10)
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )

    _choose_directional_spell(session, "Cast Weird", (8, 8))

    assert state.has_condition("goblin_1", Condition.FRIGHTENED)
    health_after_cast = target.creature.get_health()
    resolve_end_turn_effects(state, "goblin_1")
    assert target.creature.get_health() == health_after_cast - 5


def test_sleep_progresses_from_incapacitated_to_unconscious(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Sleep", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    state.creatures["goblin_1"].position.x = state.active_position.x + 2
    state.creatures["goblin_1"].position.y = state.active_position.y
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: 1
    )

    cast = _choose_directional_spell(
        session,
        "Cast Sleep",
        (
            state.creatures["goblin_1"].position.x,
            state.creatures["goblin_1"].position.y,
        ),
    )

    assert state.has_condition("goblin_1", Condition.INCAPACITATED)
    state.initiative_order = ["player", "goblin_1"]
    state.turn_index = 1
    state.turn_engine.advance_turn(state, cast)
    assert state.has_condition("goblin_1", Condition.UNCONSCIOUS)
    assert state.has_condition("goblin_1", Condition.INCAPACITATED) is False


def test_sleep_stages_choice_when_area_contains_multiple_creatures(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Sleep", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    origin = Position(state.active_position.x + 2, state.active_position.y)
    state.creatures["goblin_1"].position = origin
    state.creatures["goblin_2"].position = Position(origin.x, origin.y + 1)
    state.creatures["goblin_3"].creature.current_health = 0
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: 1
    )

    _choose_directional_spell(
        session,
        "Cast Sleep",
        (origin.x, origin.y),
    )
    assert state.current_decision().kind == "spell_targets"
    remove_second = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target"
        and action.value == "goblin_2"
    )
    state.apply_action(remove_second)
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    state.apply_action(confirm)

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
    monkeypatch,
    statistics_change: dict[str, object],
    reason: str,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell("Sleep", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    target = state.creatures["goblin_1"]
    target.position.x = state.active_position.x + 2
    target.position.y = state.active_position.y
    target.creature.statistics = replace(
        target.creature.statistics,
        **statistics_change,
    )
    state.creatures["goblin_2"].creature.current_health = 0
    state.creatures["goblin_3"].creature.current_health = 0
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: 1
    )

    cast = _choose_directional_spell(
        session,
        "Cast Sleep",
        (target.position.x, target.position.y),
    )

    assert state.has_condition("goblin_1", Condition.INCAPACITATED) is False
    save = next(
        event.data["save_details"][0]
        for event in cast.events
        if event.type == "spell_cast"
    )
    assert save["automatic_success_reasons"] == [reason]


def test_charm_person_save_has_advantage_against_opponent(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell(
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
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: next(rolls),
    )

    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("charm_person:goblin_1")
    )
    cast = state.apply_action(action)

    assert state.has_condition("goblin_1", Condition.CHARMED) is False
    save = next(
        event.data["save_details"][0]
        for event in cast.events
        if event.type == "spell_cast"
    )
    assert save["die"] == 20


def test_adjacent_creature_can_spend_action_to_wake_sleep_target() -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    state._apply_effects(
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "concentration",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "definition_id": "sleep",
                    "parameters": {
                        "end_events": [
                            ["adjacent_creature_wakes_target", "any"]
                        ]
                    },
                },
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
    state.turn_index = 0

    action = next(
        action
        for action in state._creature_action_candidates("goblin_2")
        if action.kind == "wake_spell_target"
        and action.value == "goblin_1"
    )
    result = state._execute_creature_action(action, state.current_decision())

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
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    target_ref = "goblin_1"
    state._apply_effects(
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref=target_ref,
                data={
                    "effect_kind": "spell",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "definition_id": definition_id,
                    "parameters": {"end_events": [[event, "any"]]},
                },
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
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    state._apply_effects(
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "spell",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "definition_id": "charm_person",
                    "parameters": {
                        "end_events": [["target_damaged", "source_team"]]
                    },
                },
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


def test_hideous_laughter_damage_save_has_advantage(monkeypatch) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    state._apply_effects(
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "concentration",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "definition_id": "hideous_laughter",
                    "parameters": {
                        "damage_repeat_save_advantage": True,
                        "save_ability": "wisdom",
                        "save_dc": 15,
                    },
                },
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
    monkeypatch.setattr(
        "srd_arena.domain.encounters.ongoing_effects._roll_die",
        lambda _sides: next(rolls),
    )

    resolve_spell_lifecycle_event(
        state,
        "target_damaged",
        actor_ref="player",
        target_ref="goblin_1",
    )

    assert state.ongoing_effects == []
    assert state.has_condition("goblin_1", Condition.INCAPACITATED) is False


def test_hideous_laughter_prevents_target_from_removing_its_own_prone(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        build_spell(
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
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: 1
    )
    action = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("hideous_laughter:goblin_1")
    )
    state.apply_action(action)

    state._remove_condition(
        "goblin_1",
        Condition.PRONE,
        removed_by_ref="goblin_1",
    )
    assert state.has_condition("goblin_1", Condition.PRONE)

    state._remove_condition("goblin_1", Condition.PRONE)
    assert state.has_condition("goblin_1", Condition.PRONE) is False


def test_new_concentration_replaces_the_previous_effect_tree() -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state

    for origin_id, target_ref in (
        ("first-cast", "goblin_1"),
        ("second-cast", "goblin_2"),
    ):
        state._apply_effects(
            [
                EffectResult(
                    kind="start_ongoing_effect",
                    target_ref=target_ref,
                    data={
                        "effect_kind": "concentration",
                        "source_ref": "player",
                        "source_label": "Traveler",
                        "definition_id": "hold_person",
                        "parameters": {},
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


def test_failed_damage_save_ends_concentration_and_its_conditions(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    state._apply_effects(
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="goblin_1",
                data={
                    "effect_kind": "concentration",
                    "source_ref": "player",
                    "source_label": "Traveler",
                    "definition_id": "hold_person",
                    "parameters": {},
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
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )

    resolve_concentration_damage(state, "player", 20)

    assert state.ongoing_effects == []
    assert state.has_condition("goblin_1", Condition.PARALYZED) is False


def test_advance_until_next_decision_runs_enemy_turns_until_player_turn() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.turn_index = 1

    progress = session.encounter_state.advance_until_next_decision()

    assert progress.transition is None
    assert ("system", "Goblin Warrior moves down-left to (4, 3).") in progress.messages
    assert session.encounter_state.active_creature() == "player"
    assert session.encounter_state.round_number == 2


def test_archer_behavior_uses_ranged_weapon_without_closing_distance(
    monkeypatch,
) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    enemy = session.encounter_state.creatures["goblin_1"]
    enemy.behavior.type = "archer"
    session.encounter_state._initialize_action_selectors()
    session.encounter_state.creatures["goblin_2"].creature.current_health = 0
    session.encounter_state.creatures["goblin_3"].creature.current_health = 0
    enemy.position.x = 5
    enemy.position.y = 2
    session.encounter_state.active_position.x = 1
    session.encounter_state.active_position.y = 6
    session.encounter_state.turn_index = 1

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 4)

    progress = session.encounter_state.advance_until_next_decision()

    attack_event = next(
        event for event in progress.events if event.type == "attack_resolved" and event.creature_ref == "goblin_1"
    )
    assert enemy.position.x == 5
    assert enemy.position.y == 2
    assert attack_event.data["attack_roll_detail"]["attack_type"] == "ranged"
    assert attack_event.data["attack_roll_detail"]["weapon_name"] == "Shortbow"


def test_natural_one_is_an_automatic_miss_for_attack_rolls(monkeypatch) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    session.encounter_state.creatures["goblin_1"].creature.attributes.base_armor_class = 0
    starting_health = session.encounter_state.creatures["goblin_1"].creature.get_health()

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 1)

    attack_index = _action_id(session, "attack", "goblin_1")
    result = session.choose(attack_index)

    assert (
        "system",
        "Traveler misses Goblin Warrior (goblin_1).",
    ) in result.messages
    attack_event = next(event for event in result.events if event.type == "attack_resolved")
    assert attack_event.data["hit"] is False
    assert attack_event.data["critical_hit"] is False
    assert attack_event.data["damage"] == 0
    assert attack_event.data["damage_roll_detail"] is None
    assert attack_event.data["attack_roll_detail"]["critical_miss"] is True
    assert session.encounter_state.creatures["goblin_1"].creature.get_health() == starting_health


def test_extra_attack_allows_second_attack_after_movement(monkeypatch) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.decision_creature.combat_profile.attacks_per_attack_action = 2
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    session.encounter_state.creatures["goblin_1"].creature.current_health = 20

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 1)

    attack_index = _action_id(session, "attack", "goblin_1")
    first_result = session.choose(attack_index)

    attack_events = [event for event in first_result.events if event.type == "attack_resolved"]
    assert len(attack_events) == 1
    assert attack_events[0].data["attacks_remaining"] == 1
    assert session.encounter_state.creatures["goblin_1"].creature.get_health() == 15
    assert session.encounter_state.active_action_available is False
    assert session.encounter_state.active_attacks_remaining == 1

    move_index = _action_id_by_label(session, "Move left")
    move_result = session.choose(move_index)

    assert ("system", "Traveler moves left to (3, 3).") in move_result.messages
    assert session.encounter_state.active_position.x == 3
    assert session.encounter_state.active_position.y == 3
    assert session.encounter_state.active_attacks_remaining == 1

    second_attack_index = _action_id(session, "attack", "goblin_1")
    second_result = session.choose(second_attack_index)

    second_attack_events = [event for event in second_result.events if event.type == "attack_resolved"]
    assert len(second_attack_events) == 1
    assert second_attack_events[0].data["attacks_remaining"] == 0
    assert session.encounter_state.creatures["goblin_1"].creature.get_health() == 10
    assert session.encounter_state.active_attacks_remaining == 0
    assert not any(label.startswith("Attack enemy") for label in _action_labels(session))


def test_second_wind_appears_and_consumes_bonus_action(monkeypatch) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.decision_creature.current_health = 10

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 5)

    second_wind_index = _action_id_by_label(session, "Second Wind")
    result = session.choose(second_wind_index)

    assert ("system", "Traveler uses Second Wind.") in result.messages
    assert ("system", "Healing: 1d10=5 + level 2 = 7; applied 7.") in result.messages
    assert session.decision_creature.get_health() == 17
    assert session.encounter_state is not None
    assert session.encounter_state.active_bonus_action_available is False
    assert session.decision_creature.feature_uses_remaining["second_wind"] == 1
    second_wind = next(
        action
        for action in session.get_scene_view().action_details
        if action.label == "Second Wind"
    )
    assert second_wind.availability == "unavailable"
    assert second_wind.enabled is False
    event = next(event for event in result.events if event.type == "feature_used")
    assert event.data["feature_id"] == "second_wind"
    assert event.data["feature_name"] == "Second Wind"
    assert event.data["uses_remaining"] == 1
    assert event.data["healing_roll_detail"]["dice"] == "1d10"
    assert event.data["healing_roll_detail"]["applied_healing"] == 7


def test_second_wind_stays_visible_in_feature_column_when_unavailable(
    monkeypatch,
) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.decision_creature.current_health = 10

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 5)

    second_wind_index = _action_id_by_label(session, "Second Wind")
    session.choose(second_wind_index)

    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert "Second Wind" in _action_labels(session)
    feature_actions = {action.label: action for action in presentation.encounter.feature_actions}
    assert set(feature_actions) == {"Second Wind", "Action Surge"}
    assert feature_actions["Second Wind"].enabled is False
    assert feature_actions["Second Wind"].unavailable_reason is not None
    assert feature_actions["Second Wind"].cost["bonus_action"] == 1


def test_action_surge_grants_additional_action_for_same_turn(monkeypatch) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    session.encounter_state.creatures["goblin_1"].creature.current_health = 30

    def fixed_roll(sides: int) -> int:
        return 18 if sides == 20 else 6

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", fixed_roll)
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 6)

    first_attack_index = _action_id(session, "attack", "goblin_1")
    session.choose(first_attack_index)

    assert session.encounter_state.active_actions_remaining == 0

    action_surge_index = _action_id_by_label(session, "Action Surge")
    result = session.choose(action_surge_index)

    assert ("system", "Traveler uses Action Surge.") in result.messages
    assert session.encounter_state.active_actions_remaining == 1
    assert session.encounter_state.active_magic_actions_remaining == 0
    assert session.decision_creature.feature_uses_remaining["action_surge"] == 0
    assert any(action.kind == "attack" for action in session.get_scene_view().action_details)
    assert not any(action.kind == "spell" for action in session.get_scene_view().action_details)
    event = next(event for event in result.events if event.type == "feature_used")
    assert event.data["feature_id"] == "action_surge"
    assert event.data["granted_actions"] == 1


def test_presentation_surfaces_conditions_in_encounter_views(monkeypatch) -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 3
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 2
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5)

    _choose_directional_spell(session, "Cast Color Spray", (4, 2))
    presentation = build_session_presentation(session)

    assert presentation.encounter is not None
    assert "Blinded" in presentation.encounter.battlefield.summary_text
    assert presentation.encounter.resources.conditions == ()
    assert any(
        creature.creature_ref == "goblin_1" and creature.conditions == ("blinded",)
        for creature in presentation.encounter.battlefield.creatures
    )


def test_spell_actions_map_to_magic_menu_bucket() -> None:
    bucket = GameWindow._action_bucket_key(
        None,
        ActionView(
            id="spell-color_spray",
            label="Cast Color Spray",
            kind="spell",
            creature_ref="player",
            value="color_spray",
            cost={"action": 1},
        ),
    )

    assert bucket == "magic"


def test_grapple_actions_map_to_attack_menu_bucket() -> None:
    bucket = GameWindow._action_bucket_key(
        None,
        ActionView(
            id="player-grapple-0",
            label="Grapple enemy 1 (Goblin Warrior)",
            kind="grapple",
            creature_ref="player",
            value=0,
            cost={"action": 1},
        ),
    )

    assert bucket == "attack"


def test_grapple_actions_share_one_board_targeting_mode() -> None:
    window = GameWindow.__new__(GameWindow)
    actions = [
        ActionView(
            id=f"player-grapple-{index}",
            label=f"Grapple target {index}",
            kind="grapple",
            creature_ref="player",
            value=f"goblin_{index + 1}",
            cost={"action": 1},
        )
        for index in range(2)
    ]

    modes = GameWindow._target_selection_modes(window, actions)

    mode = TargetSelectionMode(kind="grapple", source_trigger_id="grapple")
    assert set(modes) == {mode}
    assert set(modes[mode]) == {"goblin_1", "goblin_2"}
    assert GameWindow._target_mode_label(window, mode) == "Grapple"


def test_attack_sources_have_distinct_board_targeting_modes() -> None:
    window = GameWindow.__new__(GameWindow)
    actions = [
        ActionView(
            id="goblin-scimitar-player",
            label="Scimitar player",
            kind="attack",
            creature_ref="goblin",
            value="player",
            cost={"action": 1},
            preferred_attack_name="Scimitar",
        ),
        ActionView(
            id="goblin-shortbow-player",
            label="Shortbow player",
            kind="attack",
            creature_ref="goblin",
            value="player",
            cost={"action": 1},
            preferred_attack_name="Shortbow",
        ),
    ]

    modes = GameWindow._target_selection_modes(window, actions)

    scimitar = TargetSelectionMode(kind="attack", source_trigger_id="Scimitar")
    shortbow = TargetSelectionMode(kind="attack", source_trigger_id="Shortbow")
    assert set(modes) == {scimitar, shortbow}
    assert modes[scimitar]["player"].preferred_attack_name == "Scimitar"
    assert modes[shortbow]["player"].preferred_attack_name == "Shortbow"
    assert GameWindow._target_mode_label(window, scimitar) == "Scimitar"
    assert GameWindow._target_mode_label(window, shortbow) == "Shortbow"


def test_unavailable_button_tooltip_lists_all_reasons() -> None:
    class Button:
        def __init__(self) -> None:
            self.enabled = True
            self.properties = {}
            self.tooltip = ""

        def setProperty(self, name, value) -> None:
            self.properties[name] = value

        def setEnabled(self, enabled) -> None:
            self.enabled = enabled

        def setToolTip(self, tooltip) -> None:
            self.tooltip = tooltip

    button = Button()
    actions = [
        ActionView(
            id="rend-target-1",
            label="Rend",
            kind="attack",
            creature_ref="dragon",
            enabled=False,
            availability="unavailable",
            unavailable_reasons=(
                "No Action remains.",
                "The target is out of range.",
            ),
        ),
        ActionView(
            id="rend-target-2",
            label="Rend",
            kind="attack",
            creature_ref="dragon",
            enabled=False,
            availability="unavailable",
            unavailable_reasons=(
                "No Action remains.",
                "The target is not available.",
            ),
        ),
    ]

    GameWindow._configure_action_button(button, actions)

    assert button.enabled is False
    assert button.properties["availability"] == "unavailable"
    assert button.tooltip == (
        "Unavailable:\n"
        "• No Action remains.\n"
        "• The target is out of range.\n"
        "• The target is not available."
    )


@pytest.mark.parametrize(
    ("attacks_available", "actions", "expected"),
    [
        (
            1,
            [
                ActionView(
                    id="attack-goblin",
                    label="Attack Goblin",
                    kind="attack",
                    creature_ref="player",
                    value="goblin_1",
                    cost={"action": 1},
                )
            ],
            TargetSelectionMode(kind="attack", source_trigger_id="attack"),
        ),
        (0, [], None),
        (1, [], None),
    ],
)
def test_follow_up_attack_is_queued_only_with_attacks_and_targets(
    monkeypatch,
    attacks_available,
    actions,
    expected,
) -> None:
    window = GameWindow.__new__(GameWindow)
    window.session = object()
    presentation = SimpleNamespace(
        encounter=SimpleNamespace(
            resources=SimpleNamespace(attacks_available=attacks_available),
            non_movement_actions=actions,
        )
    )
    monkeypatch.setattr(
        "srd_arena.frontends.qt.app.build_session_presentation",
        lambda _session: presentation,
    )

    attack_mode = TargetSelectionMode(kind="attack", source_trigger_id="attack")
    assert GameWindow._available_follow_up_attack_mode(window, attack_mode) == expected


def test_clicking_actor_during_follow_up_attack_reopens_movement() -> None:
    window = GameWindow.__new__(GameWindow)
    attack_mode = TargetSelectionMode(
        kind="attack",
        source_trigger_id="Shortsword",
    )
    window._pending_target_mode = attack_mode
    window._presentation = SimpleNamespace(
        encounter=SimpleNamespace(non_movement_actions=[])
    )
    planned_for: list[str] = []
    window._begin_movement_plan = planned_for.append

    GameWindow._handle_battlefield_creature_clicked(window, "assassin")

    assert planned_for == ["assassin"]


def test_allocation_target_clicks_add_and_shift_clicks_remove() -> None:
    window = GameWindow.__new__(GameWindow)
    mode = TargetSelectionMode(
        kind="toggle_spell_target",
        source_trigger_id="eldritch_blast",
    )
    window._pending_target_mode = mode
    window._presentation = SimpleNamespace(
        encounter=SimpleNamespace(
            non_movement_actions=[
                ActionView(
                    id="caster-spell-target-dummy-remove",
                    label="Remove Target Dummy (1)",
                    kind="toggle_spell_target",
                    creature_ref="caster",
                    value="target_dummy",
                    source_trigger_id="eldritch_blast",
                ),
                ActionView(
                    id="caster-spell-target-dummy-add",
                    label="Add Target Dummy (2)",
                    kind="toggle_spell_target",
                    creature_ref="caster",
                    value="target_dummy",
                    source_trigger_id="eldritch_blast",
                ),
            ]
        )
    )
    selected: list[str] = []
    window._select_action = selected.append
    window._begin_movement_plan = lambda _creature_ref: None

    GameWindow._handle_battlefield_creature_clicked(
        window,
        "target_dummy",
    )
    GameWindow._handle_battlefield_creature_clicked(
        window,
        "target_dummy",
        remove_allocation=True,
    )

    assert selected == [
        "caster-spell-target-dummy-add",
        "caster-spell-target-dummy-remove",
    ]


def test_exact_spell_allocation_auto_confirms_after_final_click(
    monkeypatch,
) -> None:
    session = Scenario(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.attributes = replace(caster.attributes, level=5)
    caster.spellcasting.learned_spells.append(
        build_spell("Eldritch Blast", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT))
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda sides: 15 if sides == 20 else 3,
    )
    initial = next(
        action
        for action in session.get_scene_view().action_details
        if action.kind == "spell"
        and str(action.value) == "eldritch_blast:goblin_1"
    )
    session.choose(initial.id)
    assert state.pending_spell_cast is not None
    add = next(
        action
        for action in session.get_scene_view().action_details
        if action.kind == "toggle_spell_target"
        and action.value == "goblin_1"
        and action.id.endswith("-add")
    )

    window = GameWindow.__new__(GameWindow)
    window.session = session
    window._presentation = build_session_presentation(session)
    window._pending_target_mode = TargetSelectionMode(
        kind="toggle_spell_target",
        source_trigger_id="eldritch_blast",
    )
    window._action_menu_scope = ActionMenuScope("action", "magic")
    window._apply_turn_result = lambda _result, **_kwargs: None

    assert GameWindow._pending_spell_allocation_counts(window) == {
        "goblin_1": 1
    }
    assert GameWindow._pending_spell_allocation_status(window) == (
        "Eldritch Blast: 1 allocation remaining (1/2 assigned)"
    )

    GameWindow._select_action(window, add.id)

    assert state.pending_spell_cast is None
    assert state.current_decision().kind == "turn"
    assert state.active_actions_remaining == 0


def test_movement_does_not_consume_pending_multiattack_slots() -> None:
    session = Scenario(
        str(STAT_BLOCK_ACTION_SCENARIO_DIR),
        start_scene="stat_block_action_showcase",
    ).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn_index = state.initiative_order.index("assassin")
    actor = state.active_creature_state
    actor.movement_remaining = None
    actor.actions_remaining = 1
    actor.magic_actions_remaining = 1
    actor.attacks_remaining = 0
    actor.pending_multiattack.clear()

    multiattack = next(
        action for action in state.available_actions() if action.kind == "multiattack"
    )
    state.apply_action(multiattack)
    slots_before = tuple(actor.pending_multiattack)

    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "left"
    )
    state.apply_action(move)

    assert tuple(actor.pending_multiattack) == slots_before
    assert actor.attacks_remaining == len(slots_before)


def test_directional_spell_target_mode_stays_available_without_creature_target_map() -> None:
    window = GameWindow.__new__(GameWindow)
    window._pending_target_mode = TargetSelectionMode(
        kind="spell",
        source_trigger_id="color_spray",
    )
    actions = [
        ActionView(
            id="spell-color_spray",
            label="Cast Color Spray",
            kind="spell",
            creature_ref="player",
            value="color_spray",
            cost={"action": 1},
        )
    ]

    assert GameWindow._target_mode_is_available(window, actions, {}) is True


def test_spell_target_modes_preserve_selected_cast_level() -> None:
    window = GameWindow.__new__(GameWindow)
    actions = [
        ActionView(
            id=f"blight-{suffix}",
            label=label,
            kind="spell",
            creature_ref="spectrum_adept",
            value=value,
            cost={"action": 1},
        )
        for suffix, label, value in (
            ("base", "Cast Blight", "blight:plant_target"),
            ("level-5", "Cast Blight (Level 5)", "blight:plant_target#slot=5"),
            ("level-6", "Cast Blight (Level 6)", "blight:plant_target#slot=6"),
        )
    ]

    modes = GameWindow._target_selection_modes(window, actions)

    assert modes[
        TargetSelectionMode(kind="spell", source_trigger_id="blight")
    ]["plant_target"].id == "blight-base"
    assert modes[
        TargetSelectionMode(
            kind="spell",
            source_trigger_id="blight",
            variant_id="Level 5",
        )
    ]["plant_target"].id == "blight-level-5"
    assert modes[
        TargetSelectionMode(
            kind="spell",
            source_trigger_id="blight",
            variant_id="Level 6",
        )
    ]["plant_target"].id == "blight-level-6"


def test_goblin_encounter_attack_can_end_scene_with_victory(monkeypatch) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.decision_creature.combat_profile.attacks_per_attack_action = 1
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    session.encounter_state.creatures["goblin_1"].creature.current_health = 1
    session.encounter_state.creatures["goblin_2"].creature.current_health = 0
    session.encounter_state.creatures["goblin_3"].creature.current_health = 0

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 4)

    attack_index = _action_id(session, "attack", "goblin_1")
    result = session.choose(attack_index)

    assert result.selected_choice_text is not None
    assert result.events[0].data["kind"] == "attack"
    assert session.current_scene_id == "goblin_encounter"
    assert session.pending_scene_transition is not None
    assert session.encounter_state is not None
    assert result.scene_changed is False
    assert result.scene.action_details[0].id == "system-continue-scene-transition"


def test_attack_consumes_action_until_next_turn(monkeypatch) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.decision_creature.combat_profile.attacks_per_attack_action = 1
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 1)

    attack_index = _action_id(session, "attack", "goblin_1")
    session.choose(attack_index)

    assert session.encounter_state.active_action_available is False
    attacks = [
        action
        for action in session.get_scene_view().action_details
        if action.kind == "attack"
    ]
    assert attacks
    assert all(action.availability == "unavailable" for action in attacks)

    wait_index = _action_id_by_label(session, "Wait")
    session.choose(wait_index)
    while session.encounter_state.current_decision().kind == "reaction":
        session.choose(_action_id_by_label(session, "Pass reaction"))

    assert session.encounter_state.creatures["player"].actions_remaining == 1
    assert any(action.kind == "attack" for action in session.get_scene_view().action_details)


def test_encounter_victory_waits_for_continue_before_restart() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    for creature_ref, creature_state in session.encounter_state.creatures.items():
        if creature_ref != session.encounter_state.current_decision().creature_ref:
            creature_state.creature.current_health = 0

    wait_index = _action_id_by_label(session, "Wait")
    result = session.choose(wait_index)

    assert result.scene_changed is False
    assert session.current_scene_id == "goblin_encounter"
    assert session.pending_scene_transition is not None
    assert session.encounter_state is not None
    assert ("system", "Victory! Press continue to proceed.") in result.messages
    assert result.scene.scene_text == "Victory! Press continue to proceed."
    assert session.pending_scene_transition.message == "Victory! Press continue to proceed."
    assert result.scene.action_details[0].id == "system-continue-scene-transition"

    continue_result = session.choose("system-continue-scene-transition")

    assert continue_result.scene_changed is False
    assert session.pending_scene_transition is None
    assert session.current_scene_id == "goblin_encounter"
    assert session.encounter_state is not None
    assert all(
        creature_state.creature.get_health() > 0
        for creature_ref, creature_state in session.encounter_state.creatures.items()
        if creature_ref != session.encounter_state.current_decision().creature_ref
    )
