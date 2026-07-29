from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace

import pytest

from srd_arena.domain.encounters.encounter import ActionCost, EncounterAction, EncounterState
from srd_arena.domain.encounters.actions.hit_effects import (
    apply_attack_hit_effects,
)
from srd_arena.domain.encounters.models import EncounterProgress
from srd_arena.frontends.shared.combat import render_encounter_text
from srd_arena.runtime.scenario import Scenario
from srd_arena.frontends.qt.app import GameWindow
from srd_arena.domain.effects import EffectResult
from srd_arena.domain.creatures import AttackActionDefinition
from srd_arena.frontends.shared.session import SpellSlotTrackView, build_session_presentation
from srd_arena.runtime.models import ActionView
from srd_arena.content.catalogs import load_bestiary_catalog
from srd_arena.content.loaders.creatures import build_creature
from srd_arena.content.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.schemas import CreatureSchema
from srd_arena.frontends.qt.ui.encounter import BattlefieldWidget
from srd_arena.frontends.qt.ui.encounter.config import TargetSelectionMode

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
TACTICAL_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "tactical_game"
MULTIATTACK_SCENARIO_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "scenarios"
    / "multiattack_showcase"
)
_ROLL_INITIATIVE = EncounterState._roll_initiative


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


def _action_index_by_prefix(session, prefix: str) -> int:
    return next(
        index
        for index, choice in enumerate(session.get_scene_view().choices)
        if choice.startswith(prefix)
    )


def _action_index(session, kind: str, value: object) -> int:
    return next(
        action.index
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
            value=f"{action.value}@{aim_cell[0] + 0.5:.4f},{aim_cell[1] + 0.5:.4f}",
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
    assert "Move up" in scene_view.choices
    assert "Move up-right" in scene_view.choices
    assert "Wait" in scene_view.choices
    assert "Flee encounter" not in scene_view.choices
    assert "Retreat until the encounter system is ready." not in scene_view.choices
    assert "Save game" not in scene_view.choices
    assert "Load game" not in scene_view.choices
    assert scene_view.choices[-1] == "Exit game"


def test_cli_encounter_renderer_generates_grid_text() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None

    scene_text = render_encounter_text(session.encounter_state, session.decision_creature)

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


def test_initiative_is_rolled_for_all_combatants_at_encounter_start(monkeypatch) -> None:
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
    assert [
        creature.token_image for creature in presentation.encounter.battlefield.creatures
    ] == [
        "tokens/traveler.png",
        "tokens/goblin.png",
        "tokens/goblin.png",
        "tokens/goblin.png",
    ]
    assert [
        creature.team_color
        for creature in presentation.encounter.battlefield.creatures
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
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    scene_view = session.get_scene_view()
    move_up_index = scene_view.choices.index("Move up")
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

    move_index = session.get_scene_view().choices.index("Move up-right")
    result = session.choose(move_index)

    assert ("system", "Traveler moves up-right to (2, 5).") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.active_position.x == 2
    assert session.encounter_state.active_position.y == 5


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

    multiattack = next(
        action
        for action in state.available_actions(session.decision_creature)
        if action.kind == "multiattack"
    )
    initial_actions = state.available_actions(session.decision_creature)
    assert multiattack.value is None
    assert not any(action.kind == "attack" for action in initial_actions)

    started = state.apply_action(session.decision_creature, multiattack)

    assert state.active_creature_state.actions_remaining == 0
    assert state.active_creature_state.attacks_remaining == 2
    assert [
        invocation.name
        for invocation in state.active_creature_state.pending_multiattack
    ] == [
        "Thunderous Slam",
        "Thunderous Slam",
    ]
    assert not any(event.type == "attack_resolved" for event in started.events)

    invocation = next(
        action
        for action in state.available_actions(session.decision_creature)
        if action.kind == "attack" and action.value == "goblin_1"
    )
    assert invocation.source_trigger_id == "Thunderous Slam"
    first = state.apply_action(session.decision_creature, invocation)

    assert state.active_creature_state.attacks_remaining == 1
    assert [
        invocation.name
        for invocation in state.active_creature_state.pending_multiattack
    ] == ["Thunderous Slam"]
    assert [
        event.data["attack_name"]
        for event in first.events
        if event.type == "attack_resolved"
    ] == ["Thunderous Slam"]

    second_invocation = next(
        action
        for action in state.available_actions(session.decision_creature)
        if action.kind == "attack" and action.value == "goblin_1"
    )
    second = state.apply_action(session.decision_creature, second_invocation)

    assert state.active_creature_state.attacks_remaining == 0
    assert state.active_creature_state.pending_multiattack == []
    assert [
        event.data["attack_name"]
        for event in second.events
        if event.type == "attack_resolved"
    ] == ["Thunderous Slam"]


def test_multiattack_showcase_loads_enriched_creatures() -> None:
    scenario = Scenario(MULTIATTACK_SCENARIO_DIR)
    session = scenario.create_session()
    session.get_scene_view()

    assert scenario.display_name == "Multiattack Showcase"
    assert session.encounter_state is not None
    creatures = {
        state.creature.id: state.creature
        for state in session.encounter_state.creatures.values()
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
    assert {
        creature["controller"] for creature in runtime_creatures.values()
    } == {"external"}


def test_aboleth_tentacle_grapples_and_exposes_fixed_dc_escape(
    monkeypatch,
) -> None:
    session = Scenario(MULTIATTACK_SCENARIO_DIR).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
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

    multiattack = next(
        action
        for action in state.available_actions(session.decision_creature)
        if action.kind == "multiattack"
    )
    state.apply_action(session.decision_creature, multiattack)
    tentacle = next(
        action
        for action in state.available_actions(session.decision_creature)
        if action.kind == "attack" and action.value == "air_elemental"
    )
    state.apply_action(session.decision_creature, tentacle)

    grapple = next(
        status
        for status in state.conditions_for("air_elemental")
        if status.name == "grappled"
    )
    assert grapple.source_ref == "aboleth"
    assert grapple.metadata["escape_dc"] == 14
    assert state._grappling_targets_for("aboleth") == (
        "air_elemental",
    )

    huge_target_tentacle = next(
        action
        for action in state.available_actions(session.decision_creature)
        if action.kind == "attack" and action.value == "player"
    )
    state.apply_action(session.decision_creature, huge_target_tentacle)
    assert state.has_condition("player", "grappled") is False

    state.initiative_order = ["air_elemental", "aboleth", "player"]
    state.turn_index = 0
    state.creatures["air_elemental"].actions_remaining = 1
    failed_escape = next(
        action
        for action in state.available_actions(session.decision_creature)
        if action.kind == "escape_grapple"
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )
    failed = state.apply_action(session.decision_creature, failed_escape)
    assert state.has_condition("air_elemental", "grappled") is True
    assert state.creatures["air_elemental"].actions_remaining == 0
    assert any("fails to escape" in text for _, text in failed.messages)

    state.creatures["air_elemental"].actions_remaining = 1
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 20,
    )
    escape = next(
        action
        for action in state.available_actions(session.decision_creature)
        if action.kind == "escape_grapple"
    )
    result = state.apply_action(session.decision_creature, escape)

    assert escape.label == "Escape The Deep One (DC 14)"
    assert state.has_condition("air_elemental", "grappled") is False
    assert state.has_condition("aboleth", "grappling") is False
    assert any("escapes The Deep One's grapple" in text for _, text in result.messages)


def test_tentacle_grapple_enforces_capacity_without_counting_duplicates() -> None:
    session = Scenario(MULTIATTACK_SCENARIO_DIR).create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    aboleth_ref = "aboleth"
    template = state.creatures["air_elemental"]
    for index in range(4):
        state.creatures[f"tentacle-target:{index}"] = deepcopy(template)
    tentacle = state.creatures[aboleth_ref].creature.stat_block_actions[
        "Tentacle"
    ]
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
    assert state.has_condition("tentacle-target:3", "grappled") is False


def test_fallback_tokens_use_team_colors() -> None:
    blue_fill, blue_border = BattlefieldWidget._fallback_token_colors(
        "#3f7fd5"
    )
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
    state._apply_effects(
        [
            EffectResult(
                kind="apply_status",
                target_ref="player",
                data={
                    "condition": "grappled",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            ),
            EffectResult(
                kind="apply_status",
                target_ref="goblin_1",
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
            session.decision_creature,
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
            session.decision_creature,
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
    grapple_index = _action_index(session, "grapple", "goblin_1")
    result = session.choose(grapple_index)

    assert (
        "system",
        "Traveler grapples Goblin Warrior (goblin_1).",
    ) in result.messages
    assert session.encounter_state.has_condition("goblin_1", "grappled") is True
    assert session.encounter_state.has_condition("player", "grappling") is True
    assert any(
        action.kind == "grapple" and action.value == "goblin_1"
        for action in scene_view.action_details
    )


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

    session.choose(_action_index(session, "grapple", "goblin_1"))

    assert state.active_action_available is False
    assert state.active_attacks_remaining == 1
    assert any(
        action.kind == "attack"
        for action in state.available_actions(session.decision_creature)
    )


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

    session.choose(_action_index(session, "attack", "goblin_1"))
    assert state.active_attacks_remaining == 1

    session.choose(_action_index(session, "grapple", "goblin_1"))

    assert state.active_attacks_remaining == 0
    assert not any(
        action.kind in {"attack", "grapple"}
        for action in state.available_actions(session.decision_creature)
    )


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
    state._apply_effects(
        [
            EffectResult(
                kind="apply_status",
                target_ref="player",
                data={
                    "condition": "grappling",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            ),
            EffectResult(
                kind="apply_status",
                target_ref="goblin_1",
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
        scene_view = session.get_scene_view()
        move_right_index = scene_view.choices.index("Move right")
        result = session.choose(move_right_index)

    assert ("system", "Traveler moves right to (7, 6).") in result.messages
    assert session.encounter_state is not None
    assert session.encounter_state.turn_index == 0
    assert session.encounter_state.round_number == 1
    assert session.get_scene_view().choices.count("Wait") == 1


def test_goblin_encounter_wait_advances_enemy_turns() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"

    move_up_index = session.get_scene_view().choices.index("Move up")
    session.choose(move_up_index)
    wait_index = session.get_scene_view().choices.index("Wait")
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

    assert "Cast Color Spray" in session.get_scene_view().choices


def test_burning_hands_appears_as_spell_action_when_enemy_is_in_range() -> None:
    session = Scenario(str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2

    assert "Cast Burning Hands" in session.get_scene_view().choices


def test_presentation_derives_spell_slot_rows_from_player_spellcasting(monkeypatch) -> None:
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
                kind="apply_status",
                target_ref="player",
                data={
                    "condition": "blinded",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            )
        ]
    )

    assert "Cast Lesser Restoration" in session.get_scene_view().choices


def test_color_spray_consumes_slot_and_applies_blinded_on_failed_save(monkeypatch) -> None:
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

    assert ("system", "Traveler casts Color Spray on Goblin Warrior.") in result.messages
    assert any("is blinded until the end of your next turn" in message for _, message in result.messages)
    assert session.encounter_state.active_action_available is False
    assert session.decision_creature.spellcasting.spell_slots_remaining[1] == 3
    assert session.encounter_state.has_condition("goblin_1", "blinded") is True
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

    assert state.has_condition("goblin_1", "blinded") is True
    assert state.has_condition("goblin_2", "blinded") is True
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

    assert state.has_condition("goblin_1", "blinded") is True
    assert state.has_condition("goblin_2", "blinded") is True
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
    assert spell_event.data["damage_roll_details"][0]["applied_damage"] == 6
    assert spell_event.data["damage_roll_details"][1]["applied_damage"] == 7
    assert state.creatures["goblin_1"].creature.get_health() == 4
    assert state.creatures["goblin_2"].creature.get_health() == 3
    assert any("takes 6 fire damage." in message for _, message in result.messages)
    assert any("takes 7 fire damage on a successful save." in message for _, message in result.messages)
    assert not any("Enemy 2 (Goblin Warrior) is defeated." == message for _, message in result.messages)


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


def test_battlefield_widget_preview_overlay_reaims_directional_area(monkeypatch) -> None:
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
    result = session.choose(session.get_scene_view().choices.index("Wait"))

    attack_event = next(
        event
        for event in result.events
        if event.type == "attack_resolved" and event.creature_ref == "goblin_1"
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


def test_blinded_from_color_spray_expires_at_end_of_players_next_turn(monkeypatch) -> None:
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
    session.choose(session.get_scene_view().choices.index("Wait"))

    assert state.has_condition("goblin_1", "blinded") is True

    session.choose(session.get_scene_view().choices.index("Wait"))

    assert state.has_condition("goblin_1", "blinded") is False


def test_reapplying_blinded_refreshes_duration_without_duplication(monkeypatch) -> None:
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
    session.choose(session.get_scene_view().choices.index("Wait"))
    _choose_directional_spell(session, "Cast Color Spray", (4, 1))

    assert state.has_condition("goblin_1", "blinded") is True
    assert len(state.conditions_for("goblin_1")) == 1

    session.choose(session.get_scene_view().choices.index("Wait"))
    assert state.has_condition("goblin_1", "blinded") is True

    session.choose(session.get_scene_view().choices.index("Wait"))
    assert state.has_condition("goblin_1", "blinded") is False


def test_remove_status_effect_clears_blinded_rules_immediately() -> None:
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
                kind="apply_status",
                target_ref="goblin_1",
                data={
                    "condition": "blinded",
                    "source_ref": "player",
                    "source_label": "Traveler",
                },
            )
        ]
    )
    assert state.has_condition("goblin_1", "blinded") is True
    assert state._attack_roll_mode_for(
        "player",
        "goblin_1",
        "melee",
        state.active_position,
        (state.creatures["goblin_1"].position,),
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
                target_ref="goblin_1",
                data={"condition": "blinded"},
            ),
        ]
    )

    assert messages == [("system", "Status removed.")]
    assert state.has_condition("goblin_1", "blinded") is False
    assert state._attack_roll_mode_for(
        "player",
        "goblin_1",
        "melee",
        state.active_position,
        (state.creatures["goblin_1"].position,),
    ) == "normal"


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
                kind="apply_status",
                target_ref="player",
                data={
                    "condition": "blinded",
                    "source_ref": "goblin_1",
                    "source_label": "Goblin",
                },
            )
        ]
    )

    result = session.choose(_action_index_by_prefix(session, "Cast Lesser Restoration"))

    assert ("system", "Traveler casts Lesser Restoration on Traveler.") in result.messages
    assert ("system", "Traveler is no longer blinded.") in result.messages
    assert state.has_condition("player", "blinded") is False
    assert state.active_bonus_action_available is False
    assert state.active_action_available is True
    assert session.decision_creature.spellcasting.spell_slots_remaining[2] == 0
    spell_event = next(event for event in result.events if event.type == "spell_cast")
    assert spell_event.data["spell_name"] == "Lesser Restoration"
    assert spell_event.data["target_ref"] == "player"
    assert spell_event.data["success"] is True
    assert spell_event.data["effects"][0]["kind"] == "remove_status"


def test_lesser_restoration_uses_magic_menu_bucket() -> None:
    bucket = GameWindow._action_bucket_key(
        None,
        ActionView(
            index=0,
            id="spell-lesser-restoration-player",
            label="Cast Lesser Restoration",
            kind="spell",
            creature_ref="player",
            value="lesser_restoration:player",
            cost={"bonus_action": 1},
        ),
    )

    assert bucket == "magic"


def test_advance_until_next_decision_runs_enemy_turns_until_player_turn() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    session.encounter_state.turn_index = 1

    progress = session.encounter_state.advance_until_next_decision(session.decision_creature)

    assert progress.transition is None
    assert ("system", "Goblin Warrior moves down-left to (4, 3).") in progress.messages
    assert session.encounter_state.active_creature() == "player"
    assert session.encounter_state.round_number == 2


def test_archer_behavior_uses_ranged_weapon_without_closing_distance(monkeypatch) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()

    assert session.encounter_state is not None
    enemy = session.encounter_state.creatures["goblin_1"]
    enemy.behavior.type = "archer"
    session.encounter_state._initialize_behaviors()
    session.encounter_state.creatures["goblin_2"].creature.current_health = 0
    session.encounter_state.creatures["goblin_3"].creature.current_health = 0
    enemy.position.x = 5
    enemy.position.y = 2
    session.encounter_state.active_position.x = 1
    session.encounter_state.active_position.y = 6
    session.encounter_state.turn_index = 1

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", lambda sides: 20)
    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 4)

    progress = session.encounter_state.advance_until_next_decision(session.decision_creature)

    attack_event = next(
        event
        for event in progress.events
        if event.type == "attack_resolved" and event.creature_ref == "goblin_1"
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

    attack_index = _action_index(session, "attack", "goblin_1")
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

    attack_index = _action_index(session, "attack", "goblin_1")
    first_result = session.choose(attack_index)

    attack_events = [event for event in first_result.events if event.type == "attack_resolved"]
    assert len(attack_events) == 1
    assert attack_events[0].data["attacks_remaining"] == 1
    assert session.encounter_state.creatures["goblin_1"].creature.get_health() == 15
    assert session.encounter_state.active_action_available is False
    assert session.encounter_state.active_attacks_remaining == 1

    move_index = session.get_scene_view().choices.index("Move left")
    move_result = session.choose(move_index)

    assert ("system", "Traveler moves left to (3, 3).") in move_result.messages
    assert session.encounter_state.active_position.x == 3
    assert session.encounter_state.active_position.y == 3
    assert session.encounter_state.active_attacks_remaining == 1

    second_attack_index = _action_index(session, "attack", "goblin_1")
    second_result = session.choose(second_attack_index)

    second_attack_events = [event for event in second_result.events if event.type == "attack_resolved"]
    assert len(second_attack_events) == 1
    assert second_attack_events[0].data["attacks_remaining"] == 0
    assert session.encounter_state.creatures["goblin_1"].creature.get_health() == 10
    assert session.encounter_state.active_attacks_remaining == 0
    assert not any(
        choice.startswith("Attack enemy")
        for choice in session.get_scene_view().choices
    )


def test_second_wind_appears_and_consumes_bonus_action(monkeypatch) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.decision_creature.current_health = 10

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 5)

    scene_view = session.get_scene_view()
    second_wind_index = scene_view.choices.index("Second Wind")
    result = session.choose(second_wind_index)

    assert ("system", "Traveler uses Second Wind.") in result.messages
    assert ("system", "Healing: 1d10=5 + level 2 = 7; applied 7.") in result.messages
    assert session.decision_creature.get_health() == 17
    assert session.encounter_state is not None
    assert session.encounter_state.active_bonus_action_available is False
    assert session.decision_creature.feature_uses_remaining["second_wind"] == 1
    assert "Second Wind" not in session.get_scene_view().choices
    event = next(event for event in result.events if event.type == "feature_used")
    assert event.data["feature_id"] == "second_wind"
    assert event.data["feature_name"] == "Second Wind"
    assert event.data["uses_remaining"] == 1
    assert event.data["healing_roll_detail"]["dice"] == "1d10"
    assert event.data["healing_roll_detail"]["applied_healing"] == 7


def test_second_wind_stays_visible_in_feature_column_when_unavailable(monkeypatch) -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.decision_creature.current_health = 10

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 5)

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

    first_attack_index = _action_index(session, "attack", "goblin_1")
    session.choose(first_attack_index)

    assert session.encounter_state.active_actions_remaining == 0

    scene_view = session.get_scene_view()
    action_surge_index = scene_view.choices.index("Action Surge")
    result = session.choose(action_surge_index)

    assert ("system", "Traveler uses Action Surge.") in result.messages
    assert session.encounter_state.active_actions_remaining == 1
    assert session.encounter_state.active_magic_actions_remaining == 0
    assert session.decision_creature.feature_uses_remaining["action_surge"] == 0
    assert any(
        action.kind == "attack"
        for action in session.get_scene_view().action_details
    )
    assert not any(
        action.kind == "spell"
        for action in session.get_scene_view().action_details
    )
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
            index=0,
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
            index=0,
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
            index=index,
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


@pytest.mark.parametrize(
    ("attacks_available", "actions", "expected"),
    [
        (
            1,
            [
                ActionView(
                    index=0,
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

    assert GameWindow._available_follow_up_attack_mode(window) == expected


def test_directional_spell_target_mode_stays_available_without_creature_target_map() -> None:
    window = GameWindow.__new__(GameWindow)
    window._pending_target_mode = TargetSelectionMode(
        kind="spell",
        source_trigger_id="color_spray",
    )
    actions = [
        ActionView(
            index=0,
            id="spell-color_spray",
            label="Cast Color Spray",
            kind="spell",
            creature_ref="player",
            value="color_spray",
            cost={"action": 1},
        )
    ]

    assert GameWindow._target_mode_is_available(window, actions, {}) is True


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

    attack_index = _action_index(session, "attack", "goblin_1")
    result = session.choose(attack_index)

    assert result.selected_choice_text is not None
    assert result.events[0].data["kind"] == "attack"
    assert session.current_scene_id == "goblin_encounter"
    assert session.pending_scene_transition is not None
    assert session.encounter_state is not None
    assert result.scene_changed is False
    assert result.scene.choices[0] == "Continue"


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

    attack_index = _action_index(session, "attack", "goblin_1")
    session.choose(attack_index)

    assert session.encounter_state.active_action_available is False
    assert not any(
        action.kind == "attack"
        for action in session.get_scene_view().action_details
    )

    wait_index = session.get_scene_view().choices.index("Wait")
    session.choose(wait_index)
    while session.encounter_state.current_decision().kind == "reaction":
        session.choose(session.get_scene_view().choices.index("Pass reaction"))

    assert session.encounter_state.creatures["player"].actions_remaining == 1
    assert any(
        action.kind == "attack"
        for action in session.get_scene_view().action_details
    )


def test_encounter_victory_waits_for_continue_before_restart() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR), start_scene="goblin_encounter").create_session()
    session.get_scene_view()
    assert session.encounter_state is not None
    for creature_ref, creature_state in session.encounter_state.creatures.items():
        if creature_ref != session.encounter_state.current_decision().creature_ref:
            creature_state.creature.current_health = 0

    wait_index = session.get_scene_view().choices.index("Wait")
    result = session.choose(wait_index)

    assert result.scene_changed is False
    assert session.current_scene_id == "goblin_encounter"
    assert session.pending_scene_transition is not None
    assert session.encounter_state is not None
    assert ("system", "Victory! Press continue to proceed.") in result.messages
    assert result.scene.scene_text == "Victory! Press continue to proceed."
    assert session.pending_scene_transition.message == "Victory! Press continue to proceed."
    assert result.scene.choices[0] == "Continue"

    continue_result = session.choose(0)

    assert continue_result.scene_changed is False
    assert session.pending_scene_transition is None
    assert session.current_scene_id == "goblin_encounter"
    assert session.encounter_state is not None
    assert all(
        creature_state.creature.get_health() > 0
        for creature_ref, creature_state in session.encounter_state.creatures.items()
        if creature_ref != session.encounter_state.current_decision().creature_ref
    )
