"""Exercise encounter actions, conditions, movement, and stat-block rules."""

from copy import deepcopy
from dataclasses import replace

import pytest

from srd_arena.application.observations import (
    observe_session,
)
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import (
    CapabilityTarget,
    ConditionEffect,
    ConditionRequirement,
    CreatureTypeRequirement,
    DamageEffect,
    LimitedUsePool,
    OutcomeStage,
    RechargePool,
)
from srd_arena.domain.creatures import (
    AttackActionDefinition,
    AutomaticActionDefinition,
    SavingThrowActionDefinition,
)
from srd_arena.domain.effects import EffectResult
from srd_arena.domain.effects.application import condition_from_effect
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.effects.modifiers import RollModifier
from srd_arena.domain.effects.rule_effects import (
    RollAdjustment,
)
from srd_arena.domain.effects.runtime import (
    EffectSource,
    EffectSourceKind,
    OngoingEffect,
    OngoingEffectKind,
    RuntimeStateIdentity,
    UntilTurnStart,
)
from srd_arena.domain.encounters.actions.hit_effects import (
    apply_attack_hit_effects,
)
from srd_arena.domain.encounters.actions.stat_block import (
    recharge_stat_block_actions,
)
from srd_arena.domain.encounters.encounter import (
    ActionCost,
    EncounterAction,
    EncounterState,
)
from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
from srd_arena.domain.geometry import MovementCost, Position
from srd_arena.domain.rolls.saving_throws import resolve_saving_throw
from srd_arena.engine.queries import (
    DirectTargetOptionDetails,
)
from srd_arena.frontends.gui.ui.encounter import BattlefieldWidget
from srd_arena.frontends.shared.session import build_session_presentation
from srd_arena.infrastructure.scenarios import load_scenario_directory
from tests.encounter_runtime_support import (
    CONDITIONS_SHOWCASE_SCENARIO_DIR,
    FIXTURE_ENCOUNTER_DIR,
    MULTIATTACK_SCENARIO_DIR,
    STAT_BLOCK_ACTION_SCENARIO_DIR,
    TACTICAL_SCENARIO_DIR,
    player_first_initiative,
)
from tests.encounter_runtime_support import (
    ORCHESTRATOR as _ORCHESTRATOR,
)
from tests.encounter_runtime_support import (
    ROLL_INITIATIVE as _ROLL_INITIATIVE,
)
from tests.encounter_runtime_support import (
    action_id as _action_id,
)
from tests.encounter_runtime_support import (
    action_id_by_label as _action_id_by_label,
)
from tests.encounter_runtime_support import (
    action_labels as _action_labels,
)
from tests.encounter_runtime_support import (
    as_mapping as _mapping,
)
from tests.encounter_runtime_support import (
    as_sequence as _sequence,
)

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)


def test_goblin_encounter_scene_generates_runtime_actions() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    scene_view = session.read()
    assert scene_view.scene_text is None
    labels = [action.label for action in scene_view.action_options]
    assert "Move up" in labels
    assert "Move up-right" in labels
    assert "Wait" in labels
    assert "Flee encounter" not in labels
    assert "Retreat until the encounter system is ready." not in labels
    assert "Save game" not in labels
    assert "Load game" not in labels
    assert labels[-1] == "Exit game"


def test_stat_block_action_showcase_exposes_new_runtime_capabilities() -> None:
    scenario = load_scenario_directory(str(STAT_BLOCK_ACTION_SCENARIO_DIR))
    session = scenario.create_session()
    session.current_scene_id = "stat_block_action_showcase"
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state

    avatar_actions = state._available_creature_actions("avatar")
    wyrmling_actions = state._available_creature_actions("blue_wyrmling")
    assassin_actions = state._creature_action_candidates("assassin")

    assert scenario.display_name == "Executable Stat-Block Actions"
    assert any(
        action.preferred_attack_name == "Reaping Scythe" for action in avatar_actions
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
    [assassin_slots] = state.creatures[
        "assassin"
    ].creature.multiattack.executable_slot_plans({"Shortsword", "Light Crossbow"})
    assert len(assassin_slots) == 3
    assert all(
        {option.name for option in slot.options} == {"Shortsword", "Light Crossbow"}
        for slot in assassin_slots
    )


def test_unenriched_frostwing_breath_is_present_as_unimplemented() -> None:
    session = load_scenario_directory(str(MULTIATTACK_SCENARIO_DIR)).create_session()
    session.current_scene_id = "multiattack_showcase"
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.initiative_order = ["player", "air_elemental", "aboleth"]
    state.turn.index = 0

    cold_breath = next(
        action
        for action in session.read().action_options
        if action.label == "Cold Breath"
    )

    assert cold_breath.enabled is False
    assert cold_breath.availability == "unimplemented"
    assert tuple(failure.message for failure in cold_breath.eligibility.failures) == (
        "No structured capabilities are available for this action.",
    )


def test_targeted_action_labels_only_name_the_action() -> None:
    session = load_scenario_directory(
        str(STAT_BLOCK_ACTION_SCENARIO_DIR)
    ).create_session()
    session.current_scene_id = "stat_block_action_showcase"
    session.read()
    assert session.encounter_state is not None

    actions = session.encounter_state._available_creature_actions("avatar")

    assert all(
        action.label == action.preferred_attack_name
        for action in actions
        if action.kind in {"attack", "stat_block"}
    )
    assert all(
        action.label == "Grapple" for action in actions if action.kind == "grapple"
    )


def test_line_stat_block_action_can_be_aimed_at_a_map_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()
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
    actor.creature.stat_block_actions["Lightning Breath"] = SavingThrowActionDefinition(
        name="Lightning Breath",
        target=CapabilityTarget(
            kind="area",
            shape="line",
            size_feet=30,
            width_feet=10,
        ),
        ability="dex",
        dc=30,
        failure=(
            OutcomeStage(
                effects=(DamageEffect("1d6", 0, "lightning"),),
            ),
        ),
        success=(),
        success_damage="half",
        always=(),
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
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
    actor.creature.stat_block_actions["Reaping Scythe"] = AutomaticActionDefinition(
        name="Reaping Scythe",
        target=CapabilityTarget(kind="creature", range_feet=5),
        effects=(DamageEffect("1d8", 3, "slashing"),),
        resource_pool=LimitedUsePool(
            id="stat_block_action:Reaping Scythe",
            maximum=1,
            refresh="day",
        ),
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
        event.type == "stat_block_action_resolved" for event in result.progress.events
    )
    actor.actions_remaining = 1
    assert not any(
        action.preferred_attack_name == "Reaping Scythe"
        for action in state._available_creature_actions(actor_ref)
    )


def test_saving_throw_stat_block_action_resolves_damage_and_half_on_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
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
    actor.creature.stat_block_actions["Acid Spray"] = SavingThrowActionDefinition(
        name="Acid Spray",
        target=CapabilityTarget(kind="creature", range_feet=5),
        ability="dex",
        dc=20,
        failure=(
            OutcomeStage(
                effects=(DamageEffect("2d6", 0, "acid"),),
            ),
        ),
        success=(),
        success_damage="half",
        always=(),
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
    [outcome_value] = _sequence(event.data["outcomes"])
    outcome = _mapping(outcome_value)
    assert outcome["success"] is False
    assert outcome["damage"] == min(12, health_before)


def test_unsupported_stat_block_effect_is_rejected_before_execution() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    actor_ref = state.current_decision().creature_ref
    target_ref = next(
        creature_ref
        for creature_ref in state.creatures
        if state._creatures_are_opponents(actor_ref, creature_ref)
    )
    actor = state.creatures[actor_ref]
    actor.creature.stat_block_actions["Paralyze"] = AutomaticActionDefinition(
        name="Paralyze",
        target=CapabilityTarget(kind="creature", range_feet=5),
        effects=(ConditionEffect("paralyzed"),),
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
    assert eligibility.failures[-1].code == "unsupported_stat_block_capability"
    assert actor.actions_remaining == 1


def test_recharge_stat_block_resource_becomes_available_on_required_roll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
    assert session.encounter_state is not None
    creature = session.encounter_state.active_creature_state.creature
    creature.stat_block_actions["Breath"] = AutomaticActionDefinition(
        name="Breath",
        target=CapabilityTarget(kind="creature", range_feet=5),
        effects=(DamageEffect("1d6", 0, "fire"),),
        resource_pool=RechargePool(
            id="stat_block_action:Breath",
            die_sides=6,
            minimum=5,
        ),
    )
    creature.stat_block_action_resources["Breath"] = 0
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 5,
    )

    recharge_stat_block_actions(creature)

    assert creature.stat_block_action_resources["Breath"] == 1


def test_action_eligibility_exposes_structured_failures() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
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
        cost=ActionCost(movement=MovementCost(1)),
    )

    eligibility = state.action_eligibility(move)

    assert eligibility.allowed is False
    assert {failure.code for failure in eligibility.failures} == {
        "condition.cannot_take_actions"
    }
    assert all(action.kind == "wait" for action in state.available_actions())


def test_paralyzed_blocks_actions_through_effective_incapacitation() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
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
    result = _ORCHESTRATOR.submit(state, attack)
    event = next(event for event in result.events if event.type == "attack_resolved")

    attack_roll_detail = _mapping(event.data["attack_roll_detail"])
    assert attack_roll_detail["mode"] == "advantage"
    assert event.data["critical_hit"] is True
    assert attack_roll_detail["automatic_critical_provider_ids"] == [paralyzed.id]


def test_attack_damage_uses_sourced_damage_roll_modifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    attacker_ref = state.current_decision().creature_ref
    target_ref = "goblin_1"
    state.creatures[target_ref].position = Position(
        state.active_position.x + 1,
        state.active_position.y,
    )
    state.creatures[target_ref].creature.attributes.base_armor_class = 0
    weakening = OngoingEffect(
        identity=RuntimeStateIdentity(
            id="ongoing:weakening:test",
            source=EffectSource(
                kind=EffectSourceKind.ACTION,
                definition_id="weakening_breath",
                applied_by_ref="goblin_1",
                label="Weakening Breath",
                origin_id="weakening:test",
            ),
        ),
        target_refs=(attacker_ref,),
        kind=OngoingEffectKind.GENERIC,
        rule_effects=(
            RollAdjustment(
                RollModifier(
                    roll="damage_roll",
                    mode="subtract",
                    value=2,
                )
            ),
        ),
    )
    state.ongoing_effects.append(weakening)
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 10,
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda count, _sides: 5 * count,
    )
    attack = next(
        action
        for action in state.available_actions()
        if action.kind == "attack" and action.value == target_ref
    )

    result = _ORCHESTRATOR.submit(state, attack)

    event = next(event for event in result.events if event.type == "attack_resolved")
    assert event.data["hit"] is True
    damage_roll_detail = _mapping(event.data["damage_roll_detail"])
    assert damage_roll_detail["sourced_modifier"] == -2


def test_paralyzed_target_automatically_fails_strength_and_dexterity_saves() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
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
    assert (
        state._automatic_save_failure_provider_ids_for(
            target_ref,
            "wisdom",
        )
        == ()
    )
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
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
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
    assert (
        state._automatic_critical_provider_ids_for(
            attacker_ref,
            target_ref,
        )
        == ()
    )
    assert state._automatic_save_failure_provider_ids_for(
        target_ref,
        "strength",
    ) == (stunned.id,)
    assert state._automatic_save_failure_provider_ids_for(
        target_ref,
        "dexterity",
    ) == (stunned.id,)


def test_stunned_creature_automatically_fails_dexterity_save() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
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
        automatic_failure_reasons=target.automatic_failure_reasons("dexterity"),
    )

    assert save.check.roll.selected == 20
    assert save.check.roll.total >= save.check.target
    assert save.check.success is False
    assert save.automatic_failure_reasons == (stunned.id,)


def test_action_target_requirement_uses_effective_conditions() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    actor_ref = state.current_decision().creature_ref
    target_ref = "goblin_1"
    actor = state.creatures[actor_ref].creature
    actor.stat_block_actions["Extract Brain"] = AttackActionDefinition(
        name="Extract Brain",
        attack_modes=("melee",),
        attack_bonus=0,
        target=CapabilityTarget(
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
        failure.code != "target_condition_required" for failure in eligibility.failures
    )


def test_conditions_showcase_is_externally_controlled_and_uses_immunities() -> None:
    session = load_scenario_directory(
        str(CONDITIONS_SHOWCASE_SCENARIO_DIR)
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    assert all(
        state._creature_controller(creature_ref) == "external"
        for creature_ref in state.creatures
    )
    assert Condition.POISONED in (
        state.creatures["animated_armor"].creature.statistics.condition_immunities
    )
    assert Condition.GRAPPLED in (
        state.creatures["air_elemental"].creature.statistics.condition_immunities
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
    assert hold_person.target_requirements == (CreatureTypeRequirement(("humanoid",)),)


def test_creature_type_restricted_spell_targets_are_visible_but_unavailable() -> None:
    session = load_scenario_directory(
        str(CONDITIONS_SHOWCASE_SCENARIO_DIR)
    ).create_session()
    session.read()
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
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "right"
    )
    actor = state.creatures[state.current_decision().creature_ref]
    blocker = state.creatures["goblin_1"]
    blocker.position = Position(actor.position.x + 1, actor.position.y)

    with pytest.raises(ValueError, match="destination is not free"):
        _ORCHESTRATOR.submit(state, move)


def test_initiative_is_rolled_for_all_combatants_at_encounter_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(EncounterState, "_roll_initiative", _ROLL_INITIATIVE)
    rolls = iter([12, 18, 7, 14])
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls)
    )
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    session.read()

    assert session.encounter_state is not None
    assert [
        entry.creature_ref for entry in session.encounter_state.initiative_entries
    ] == [
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


def test_presentation_exposes_initiative_tracker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(EncounterState, "_roll_initiative", _ROLL_INITIATIVE)
    rolls = iter([12, 18, 7, 14])
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls)
    )
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    presentation = build_session_presentation(observe_session(session))

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
        creature.team_color for creature in presentation.encounter.battlefield.creatures
    ] == [
        "#3f7fd5",
        "#d64545",
        "#d64545",
        "#d64545",
    ]
    assert [
        (entry.name, entry.total, entry.is_active)
        for entry in presentation.encounter.resources.initiative
    ] == [
        ("Goblin Warrior", 20, True),
        ("Goblin Warrior", 16, False),
        ("Traveler", 13, False),
        ("Goblin Warrior", 9, False),
    ]


def test_goblin_encounter_movement_consumes_movement_before_turn_advances() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
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
    assert session.encounter_state.turn.index == 0
    assert session.encounter_state.round.number == 1


def test_goblin_encounter_allows_diagonal_movement() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    move_index = _action_id_by_label(session, "Move up-right")
    result = session.choose(move_index)

    assert ("system", "Traveler moves up-right to (2, 5).") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.active_position.x == 2
    assert session.encounter_state.active_position.y == 5


def test_action_must_belong_to_current_decision_actor() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.read()
    assert session.encounter_state is not None
    action = next(
        action
        for action in session.encounter_state.available_actions()
        if action.kind == "move"
    )
    action.creature_ref = "goblin_1"

    with pytest.raises(
        ValueError,
        match="not current decision actor 'player'",
    ):
        session.choose_encounter_action(action)


def test_enriched_multiattack_queues_named_attacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()
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

    multiattack = next(
        action for action in state.available_actions() if action.kind == "multiattack"
    )
    initial_actions = state.available_actions()
    assert multiattack.value is None
    assert any(action.kind == "attack" for action in initial_actions)

    started = _ORCHESTRATOR.submit(state, multiattack)

    assert state.active_creature_state.actions_remaining == 0
    assert state.active_creature_state.attacks_remaining == 2
    assert [
        slot.options[0].name for slot in state.active_creature_state.pending_multiattack
    ] == [
        "Thunderous Slam",
        "Thunderous Slam",
    ]
    assert not any(event.type == "attack_resolved" for event in started.events)

    invocation = next(
        action
        for action in state.available_actions()
        if action.kind == "attack" and action.value == "goblin_1"
    )
    assert invocation.source_trigger_id == "Thunderous Slam"
    first = _ORCHESTRATOR.submit(state, invocation)

    assert state.active_creature_state.attacks_remaining == 1
    assert [
        slot.options[0].name for slot in state.active_creature_state.pending_multiattack
    ] == ["Thunderous Slam"]
    assert [
        event.data["attack_name"]
        for event in first.events
        if event.type == "attack_resolved"
    ] == ["Thunderous Slam"]

    second_invocation = next(
        action
        for action in state.available_actions()
        if action.kind == "attack" and action.value == "goblin_1"
    )
    second = _ORCHESTRATOR.submit(state, second_invocation)

    assert state.active_creature_state.attacks_remaining == 0
    assert state.active_creature_state.pending_multiattack == []
    assert [
        event.data["attack_name"]
        for event in second.events
        if event.type == "attack_resolved"
    ] == ["Thunderous Slam"]


def test_assassin_multiattack_applies_independent_poisoned_conditions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()
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
        action for action in state.available_actions() if action.kind == "multiattack"
    )
    assert state.action_eligibility(multiattack).allowed is True
    _ORCHESTRATOR.submit(state, multiattack)

    for _ in range(3):
        shortsword = next(
            action
            for action in state.available_actions()
            if action.kind == "attack"
            and action.value == "goblin_1"
            and action.preferred_attack_name == "Shortsword"
        )
        _ORCHESTRATOR.submit(state, shortsword)

    poisoned = [
        condition
        for condition in state.conditions_for("goblin_1")
        if condition.condition is Condition.POISONED
    ]
    assert len(poisoned) == 3
    assert len({condition.id for condition in poisoned}) == 3
    assert all(condition.source_ref == "player" for condition in poisoned)
    assert all(
        condition.duration == UntilTurnStart("player", 2) for condition in poisoned
    )

    state.turn_lifecycle.expire_conditions_for_turn_start(state, "player", 1)
    assert state.has_condition("goblin_1", Condition.POISONED) is True

    state.round.number = 2
    state.turn_lifecycle.expire_conditions_for_turn_start(state, "player", 2)
    assert state.has_condition("goblin_1", Condition.POISONED) is False


def test_multiattack_showcase_loads_enriched_creatures() -> None:
    scenario = load_scenario_directory(MULTIATTACK_SCENARIO_DIR)
    session = scenario.create_session()
    session.read()

    assert scenario.display_name == "Multiattack Showcase"
    assert session.encounter_state is not None
    state = session.encounter_state
    creatures = {
        combatant.creature.id: combatant.creature
        for combatant in state.creatures.values()
    }
    assert set(creatures) == {"player", "air_elemental", "aboleth"}
    assert creatures["player"].multiattack is not None
    player_sequence = creatures["player"].multiattack.executable_sequence(
        {
            action.name
            for action in creatures["player"].stat_block_actions.values()
            if isinstance(action, AttackActionDefinition)
        }
    )
    assert player_sequence is not None
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
    assert elemental_sequence is not None
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
    assert aboleth_sequence is not None
    assert [invocation.name for invocation in aboleth_sequence] == [
        "Tentacle",
        "Tentacle",
    ]
    assert creatures["player"].attributes.movement.speed_feet == 40
    assert creatures["air_elemental"].attributes.movement.speed_feet == 10
    assert creatures["aboleth"].attributes.movement.speed_feet == 10
    assert state.combat_rules.movement_budget(state, "player").speed.value == 80
    assert state.combat_rules.movement_budget(state, "air_elemental").speed.value == 90
    assert state.combat_rules.movement_budget(state, "aboleth").speed.value == 10
    assert {
        state._creature_controller(creature_ref) for creature_ref in state.creatures
    } == {"external"}


def test_aboleth_tentacle_grapples_and_exposes_fixed_dc_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(MULTIATTACK_SCENARIO_DIR).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.creatures["air_elemental"].creature.statistics = replace(
        state.creatures["air_elemental"].creature.statistics,
        condition_immunities=frozenset(),
    )
    state.initiative_order = ["aboleth", "air_elemental", "player"]
    state.turn.index = 0
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

    multiattack = next(
        action for action in state.available_actions() if action.kind == "multiattack"
    )
    _ORCHESTRATOR.submit(state, multiattack)
    tentacle = next(
        action
        for action in state.available_actions()
        if action.kind == "attack" and action.value == "air_elemental"
    )
    _ORCHESTRATOR.submit(state, tentacle)

    grapple = next(
        condition
        for condition in state.conditions_for("air_elemental")
        if condition.condition is Condition.GRAPPLED
    )
    assert grapple.source_ref == "aboleth"
    assert grapple.metadata["escape_dc"] == 14
    assert state._grappling_targets_for("aboleth") == ("air_elemental",)
    assert state.relationships[0].kind.value == "grappling"

    huge_target_tentacle = next(
        action
        for action in state.available_actions()
        if action.kind == "attack" and action.value == "player"
    )
    _ORCHESTRATOR.submit(state, huge_target_tentacle)
    assert state.has_condition("player", Condition.GRAPPLED) is False

    state.initiative_order = ["air_elemental", "aboleth", "player"]
    state.turn.index = 0
    state.creatures["air_elemental"].actions_remaining = 1
    failed_escape = next(
        action
        for action in state.available_actions()
        if action.kind == "escape_grapple"
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )
    failed = _ORCHESTRATOR.submit(state, failed_escape)
    assert state.has_condition("air_elemental", Condition.GRAPPLED) is True
    assert state.creatures["air_elemental"].actions_remaining == 0
    assert any("fails to escape" in text for _, text in failed.messages)

    state.creatures["air_elemental"].actions_remaining = 1
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 20,
    )
    escape = next(
        action
        for action in state.available_actions()
        if action.kind == "escape_grapple"
    )
    result = _ORCHESTRATOR.submit(state, escape)

    assert escape.label == "Escape The Deep One (DC 14)"
    assert state.has_condition("air_elemental", Condition.GRAPPLED) is False
    assert state._grappling_targets_for("aboleth") == ()
    assert any("escapes The Deep One's grapple" in text for _, text in result.messages)


def test_tentacle_grapple_enforces_capacity_without_counting_duplicates() -> None:
    session = load_scenario_directory(MULTIATTACK_SCENARIO_DIR).create_session()
    session.read()
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
                if creature_ref != state.current_decision().creature_ref
                and creature_state.is_alive
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
                if creature_ref != state.current_decision().creature_ref
                and creature_state.is_alive
            ),
        )
        == "normal"
    )


def test_grapple_action_is_available_in_the_combat_menu(
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

    rolls = iter([20, 1])
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda _sides: next(rolls)
    )

    scene_view = session.read()
    grapple_index = _action_id(session, "grapple", "goblin_1")
    result = session.choose(grapple_index)

    assert (
        "system",
        "Traveler grapples Goblin Warrior (goblin_1).",
    ) in result.messages
    assert session.encounter_state.has_condition("goblin_1", Condition.GRAPPLED) is True
    assert session.encounter_state._grappling_targets_for("player") == ("goblin_1",)
    assert any(
        action.kind == "grapple"
        and isinstance(action.details, DirectTargetOptionDetails)
        and action.details.target_ref == "goblin_1"
        for action in scene_view.action_options
    )


def test_grapple_replaces_only_one_attack_in_multiattack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()

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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.read()

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
    assert not any(
        action.kind in {"attack", "grapple"} for action in state.available_actions()
    )


def test_grappling_moves_target_and_costs_extra_movement() -> None:
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
    assert not any(
        event.type == "opportunity_attack_resolved" for event in result.events
    )
    assert state.active_movement_remaining == 4


def test_spending_last_movement_square_does_not_auto_end_turn() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    for _ in range(6):
        move_right_index = _action_id_by_label(session, "Move right")
        result = session.choose(move_right_index)

    assert ("system", "Traveler moves right to (7, 6).") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.turn.index == 0
    assert session.encounter_state.round.number == 1
    assert _action_labels(session).count("Wait") == 1


def test_goblin_encounter_wait_advances_enemy_turns() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
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
    assert session.encounter_state.turn.index == 0
    assert session.encounter_state.round.number == 2
