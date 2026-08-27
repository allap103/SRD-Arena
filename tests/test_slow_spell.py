from copy import deepcopy
from pathlib import Path

import pytest

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.spells import (
    SpellCatalog,
    build_spell as build_spell_schema,
    load_spell_catalog,
)
from srd_arena.domain.effects import EffectResult
from srd_arena.domain.effects.rule_effects import AttackLimit
from srd_arena.domain.effects.runtime import EffectPolarity, OngoingEffectKind
from srd_arena.domain.encounters import EncounterOrchestrator
from srd_arena.domain.encounters.encounter import (
    ActionCost,
    EncounterAction,
    EncounterState,
)
from srd_arena.domain.encounters.models import EncounterProgress
from srd_arena.domain.encounters.ongoing_effects import resolve_end_turn_effects
from srd_arena.domain.geometry import Position
from srd_arena.domain.spells.rules import (
    parse_spell_action_slot,
    parse_spell_action_value,
    spell_action_value,
)
from srd_arena.infrastructure.scenarios import load_scenario_directory

_ORCHESTRATOR = EncounterOrchestrator()

TACTICAL_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "tactical_game"
STAT_BLOCK_ACTION_SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "stat_block_action_showcase"
)


def _build_referenced_spell(
    name: str,
    source: str | None,
    catalog: SpellCatalog,
):
    return build_spell_schema(catalog.find(name, source))


@pytest.fixture(autouse=True)
def _player_first_initiative(monkeypatch):
    def _fixed_initiative(self):
        self.initiative_entries = []
        first_external_ref = next(
            creature_ref
            for creature_ref in self.creatures
            if self._creature_controller(creature_ref) == "external"
        )
        self.initiative_order = [
            first_external_ref,
            *(
                creature_ref
                for creature_ref in self.creatures
                if creature_ref != first_external_ref
            ),
        ]

    monkeypatch.setattr(EncounterState, "_roll_initiative", _fixed_initiative)


def _choose_directional_spell(session, label: str, aim_cell: tuple[int, int]):
    scene_view = session.get_scene_view()
    action = next(
        detail for detail in scene_view.action_details if detail.label == label
    )
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


def test_slow_cast_groups_failed_targets_under_one_typed_effect(
    monkeypatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Slow",
            "XPHB",
            load_spell_catalog(SYSTEM_CONTENT_ROOT),
        )
    )
    caster.spellcasting.spell_slots_remaining[3] = 1
    for x, target_ref in zip(
        (5, 6, 7),
        ("goblin_1", "goblin_2", "goblin_3"),
        strict=True,
    ):
        state.creatures[target_ref].position = Position(x, 5)
    base_armor_class = state.combat_rules.effective_armor_class(
        state,
        "goblin_1",
    ).value
    base_speed = state.combat_rules.movement_budget(
        state,
        "goblin_1",
    ).speed.value
    rolls = iter((1, 20, 1))
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: next(rolls),
    )

    _choose_directional_spell(session, "Cast Slow", (7, 5))

    assert state.current_decision().kind == "spell_targets"
    assert state.pending_spell_cast is not None
    assert state.pending_spell_cast.maximum_targets == 3
    confirm = next(
        action
        for action in state.available_actions()
        if action.kind == "confirm_spell_targets"
    )
    resolved = _ORCHESTRATOR.submit(state, confirm)

    assert len(state.ongoing_effects) == 1
    slow = state.ongoing_effects[0]
    assert slow.kind is OngoingEffectKind.CONCENTRATION
    assert slow.polarity is EffectPolarity.HARMFUL
    assert slow.identity.source.definition_id == "slow"
    assert slow.identity.source.applied_by_ref == "player"
    assert slow.target_refs == ("goblin_1", "goblin_3")
    assert [type(effect).__name__ for effect in slow.rule_effects] == [
        "SpeedMultiplier",
        "ArmorClassAdjustment",
        "RollAdjustment",
        "ReactionProhibition",
        "ActionEconomyRestriction",
        "AttackLimit",
        "InvocationFailureChance",
    ]
    assert state.combat_rules.effective_armor_class(
        state,
        "goblin_1",
    ).value == base_armor_class - 2
    assert state.combat_rules.movement_budget(
        state,
        "goblin_1",
    ).speed.value == base_speed // 2
    assert (
        state.combat_rules.roll_modifiers(
            state,
            "goblin_1",
            "saving_throw",
            ability="dexterity",
        ).resolve_modifier(lambda _sides: 1)
        == -2
    )
    assert (
        state.combat_rules.roll_modifiers(
            state,
            "goblin_1",
            "saving_throw",
            ability="wisdom",
        ).resolve_modifier(lambda _sides: 1)
        == 0
    )
    reaction = state.combat_rules.reaction_eligibility(
        state,
        "goblin_1",
    )
    assert reaction.allowed is False
    assert reaction.failures[-1].state_ids == (slow.identity.id,)
    spell_event = next(
        event for event in resolved.events if event.type == "spell_cast"
    )
    assert spell_event.data["area"]["shape"] == "cube"
    assert len(spell_event.data["area"]["cells"]) == 64
    assert spell_event.data["target_refs"] == [
        "goblin_1",
        "goblin_2",
        "goblin_3",
    ]
    assert [
        detail["success"] for detail in spell_event.data["save_details"]
    ] == [False, True, False]
    exported = next(
        effect
        for effect in state.export_state()["ongoing_effects"]
        if effect["id"] == slow.identity.id
    )
    assert [
        effect["type"] for effect in exported["rule_effects"]
    ] == [
        "speed_multiplier",
        "armor_class_adjustment",
        "roll_adjustment",
        "reaction_prohibition",
        "action_economy_restriction",
        "attack_limit",
        "invocation_failure_chance",
    ]
    repeat_progress = EncounterProgress()
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 20,
    )

    resolve_end_turn_effects(
        state,
        "goblin_1",
        repeat_progress,
    )

    assert state.ongoing_effects[0].target_refs == ("goblin_3",)
    assert state.combat_rules.effective_armor_class(
        state,
        "goblin_1",
    ).value == base_armor_class
    assert state.combat_rules.reaction_eligibility(
        state,
        "goblin_1",
    ).allowed
    assert not state.combat_rules.reaction_eligibility(
        state,
        "goblin_3",
    ).allowed
    resolve_end_turn_effects(
        state,
        "goblin_3",
        repeat_progress,
    )
    assert state.ongoing_effects == []
    assert sum(
        "succeeds on the repeated Wisdom save against Slow" in text
        for _, text in repeat_progress.messages
    ) == 2


def test_slow_chosen_area_never_exceeds_six_targets(monkeypatch) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Slow",
            "XPHB",
            load_spell_catalog(SYSTEM_CONTENT_ROOT),
        )
    )
    caster.spellcasting.spell_slots_remaining[3] = 1
    target_refs = [f"goblin_{index}" for index in range(1, 8)]
    for index, target_ref in enumerate(target_refs, start=5):
        if target_ref not in state.creatures:
            state.creatures[target_ref] = deepcopy(state.creatures["goblin_1"])
        state.creatures[target_ref].position = Position(index, 6)
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )

    _choose_directional_spell(session, "Cast Slow", (8, 6))

    assert state.current_decision().kind == "spell_targets"
    assert state.pending_spell_cast is not None
    assert state.pending_spell_cast.maximum_targets == 6
    assert len(state.pending_spell_cast.selected_target_refs) == 6
    selected = set(state.pending_spell_cast.selected_target_refs)
    unselected = next(target_ref for target_ref in target_refs if target_ref not in selected)
    remove = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target"
        and action.value in selected
    )
    _ORCHESTRATOR.submit(state, remove)
    add = next(
        action
        for action in state.available_actions()
        if action.kind == "toggle_spell_target"
        and action.value == unselected
    )
    _ORCHESTRATOR.submit(state, add)

    assert state.pending_spell_cast is not None
    assert len(state.pending_spell_cast.selected_target_refs) == 6


def _assassin_showcase_state() -> EncounterState:
    session = load_scenario_directory(
        str(STAT_BLOCK_ACTION_SCENARIO_DIR),
        start_scene="stat_block_action_showcase",
    ).create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn_index = state.initiative_order.index("assassin")
    assassin = state.active_creature_state
    assassin.actions_remaining = 1
    assassin.attacks_remaining = 0
    assassin.attack_action_base_attacks = 0
    assassin.attack_action_attacks_used = 0
    assassin.pending_multiattack.clear()
    state.creatures["assassin_target"].creature.current_health = 500
    return state


def test_slow_limits_attacks_made_through_multiattack(monkeypatch) -> None:
    state = _assassin_showcase_state()
    assassin = state.active_creature_state
    state._apply_effects(
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="assassin",
                data={
                    "effect_kind": "spell",
                    "source_ref": "avatar",
                    "source_label": "Slow",
                    "definition_id": "slow",
                    "parameters": {},
                },
                rule_effects=(AttackLimit(1),),
            )
        ],
        origin_id="slow-multiattack-scope",
    )

    multiattack = next(
        action for action in state.available_actions() if action.kind == "multiattack"
    )
    _ORCHESTRATOR.submit(state, multiattack)

    assert len(assassin.pending_multiattack) == 3
    assert assassin.attack_action_base_attacks == 3
    assert assassin.attack_action_attacks_used == 0
    assert assassin.attacks_remaining == 1

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 20,
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda count, _sides: count,
    )
    light_crossbow = next(
        action
        for action in state.available_actions()
        if action.kind == "attack"
        and action.value == "assassin_target"
        and action.preferred_attack_name == "Light Crossbow"
    )
    resolved = _ORCHESTRATOR.submit(state, light_crossbow)

    assert len(assassin.pending_multiattack) == 2
    assert assassin.attack_action_attacks_used == 1
    assert assassin.attacks_remaining == 0
    assert not any(action.kind == "attack" for action in state.available_actions())
    attack_event = next(
        event for event in resolved.events if event.type == "attack_resolved"
    )
    assert attack_event.data["attacks_remaining"] == 0


def test_ending_slow_mid_multiattack_restores_pending_attacks(
    monkeypatch,
) -> None:
    state = _assassin_showcase_state()
    assassin = state.active_creature_state
    state._apply_effects(
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="assassin",
                data={
                    "effect_kind": "concentration",
                    "source_ref": "assassin_target",
                    "source_label": "Slow",
                    "definition_id": "slow",
                    "parameters": {"effect_label": "Slow"},
                },
                rule_effects=(AttackLimit(1),),
            )
        ],
        origin_id="slow-breakable-multiattack",
    )
    rolls = iter((20, 1))
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: next(rolls),
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda count, _sides: count,
    )

    multiattack = next(
        action for action in state.available_actions() if action.kind == "multiattack"
    )
    _ORCHESTRATOR.submit(state, multiattack)
    assert assassin.attacks_remaining == 1

    light_crossbow = next(
        action
        for action in state.available_actions()
        if action.kind == "attack"
        and action.value == "assassin_target"
        and action.preferred_attack_name == "Light Crossbow"
    )
    resolved = _ORCHESTRATOR.submit(state, light_crossbow)

    assert state.ongoing_effects == []
    assert len(assassin.pending_multiattack) == 2
    assert assassin.attack_action_attacks_used == 1
    assert assassin.attacks_remaining == 2
    assert (
        "system",
        "Assassin Target loses concentration on Slow "
        "(Constitution 1 vs DC 10).",
    ) in resolved.messages


def test_slow_from_a_real_cast_can_fail_a_somatic_spell(
    monkeypatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    caster = session.decision_creature
    assert caster.spellcasting is not None
    catalog = load_spell_catalog(SYSTEM_CONTENT_ROOT)
    caster.spellcasting.learned_spells.extend(
        [
            _build_referenced_spell("Slow", "XPHB", catalog),
            _build_referenced_spell("Cure Wounds", "XPHB", catalog),
        ]
    )
    caster.spellcasting.spell_slots_remaining[3] = 1
    caster.spellcasting.spell_slots_remaining[1] = 1
    caster.current_health = caster.get_max_health() - 5
    rolls = iter((1, 1))
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: next(rolls),
    )

    _choose_directional_spell(
        session,
        "Cast Slow",
        (state.active_position.x, state.active_position.y),
    )

    assert state.ongoing_effects[0].target_refs == ("player",)
    state.active_creature_state.actions_remaining = 1
    state.active_creature_state.action_used_this_turn = False
    state.active_creature_state.magic_actions_remaining = 1
    initial_health = caster.get_health()
    cure = next(
        action
        for action in state.available_actions()
        if action.kind == "spell"
        and str(action.value).startswith("cure_wounds:player")
    )
    failed = _ORCHESTRATOR.submit(state, cure)

    assert caster.get_health() == initial_health
    assert caster.spellcasting.spell_slots_remaining[1] == 0
    assert state.active_actions_remaining == 0
    assert not any(event.type == "spell_cast" for event in failed.events)
    invocation_check = next(
        event
        for event in failed.events
        if event.type == "invocation_start_checked"
    )
    assert invocation_check.data["allowed"] is False
    assert invocation_check.data["checks"][0]["code"] == (
        "slow.somatic_spell_failure"
    )
    second_wind = next(
        action
        for action in state._creature_action_candidates("player")
        if action.label == "Second Wind"
    )
    compatibility = state.combat_rules.action_compatibility(
        state,
        "player",
        second_wind,
    )
    assert compatibility.allowed is False
    assert compatibility.failures[-1].code == "effect.action_economy_conflict"


def test_ending_slow_mid_attack_restores_unused_extra_attack(
    monkeypatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR),
        start_scene="goblin_encounter",
    ).create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    state = session.encounter_state
    actor = state.active_creature_state
    actor.creature.combat_profile.attacks_per_attack_action = 2
    actor.position = Position(4, 3)
    state.creatures["goblin_1"].position = Position(4, 2)
    state.creatures["goblin_1"].creature.current_health = 20
    state._apply_effects(
        [
            EffectResult(
                kind="start_ongoing_effect",
                target_ref="player",
                data={
                    "effect_kind": "concentration",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin Warrior",
                    "definition_id": "slow",
                    "parameters": {"effect_label": "Slow"},
                },
                rule_effects=(AttackLimit(1),),
            )
        ],
        origin_id="slow-breakable-concentration",
    )
    rolls = iter((20, 1))
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: next(rolls),
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice",
        lambda _count, _sides: 1,
    )

    attack = next(
        action
        for action in state.available_actions()
        if action.kind == "attack" and action.value == "goblin_1"
    )
    resolved = _ORCHESTRATOR.submit(state, attack)

    assert state.ongoing_effects == []
    assert actor.attack_action_base_attacks == 2
    assert actor.attack_action_attacks_used == 1
    assert actor.attacks_remaining == 1
    assert any(
        action.kind == "attack" and action.value == "goblin_1"
        for action in state.available_actions()
    )
    assert (
        "system",
        "Goblin Warrior loses concentration on Slow "
        "(Constitution 1 vs DC 10).",
    ) in resolved.messages
