"""Exercise core encounter orchestration, presentation, and turn resources."""

from dataclasses import replace
from types import SimpleNamespace
from typing import cast as type_cast

import pytest
from PySide6.QtWidgets import QPushButton

from srd_arena.application.game import RunningGame
from srd_arena.application.observations import (
    ActionObservation,
    ActionReasonObservation,
    observe_session,
)
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.spells import (
    load_spell_catalog,
)
from srd_arena.domain.encounters.state_initialization import (
    initialize_action_selectors,
)
from srd_arena.engine.queries import (
    SpellOptionDetails,
)
from srd_arena.frontends.gui.app import GameWindow
from srd_arena.frontends.gui.presentation.session import build_session_presentation
from srd_arena.frontends.gui.presenter import GamePresenter
from srd_arena.frontends.gui.ui.encounter.action_menus import action_bucket
from srd_arena.frontends.gui.ui.encounter.config import (
    ActionMenuScope,
    TargetSelectionMode,
)
from srd_arena.frontends.gui.ui.encounter.panel_renderer import (
    configure_action_button,
)
from srd_arena.frontends.gui.ui.encounter.targeting import (
    allocation_counts,
    allocation_status,
    mode_is_available,
    mode_label,
    selection_modes,
)
from srd_arena.infrastructure.scenarios import load_scenario_directory
from tests.encounter_runtime_support import (
    FIXTURE_ENCOUNTER_DIR,
    STAT_BLOCK_ACTION_SCENARIO_DIR,
    TACTICAL_SCENARIO_DIR,
    player_first_initiative,
)
from tests.encounter_runtime_support import (
    ORCHESTRATOR as _ORCHESTRATOR,
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
    active_creature as _active_creature,
)
from tests.encounter_runtime_support import (
    as_mapping as _mapping,
)
from tests.encounter_runtime_support import (
    build_referenced_spell as _build_referenced_spell,
)
from tests.encounter_runtime_support import (
    choose_directional_spell as _choose_directional_spell,
)

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)


def test_orchestrator_runs_enemy_turns_until_player_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()

    assert session.encounter_state is not None
    session.encounter_state.turn.index = 1
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda _sides: 1,
    )

    progress = _ORCHESTRATOR.advance(session.encounter_state)

    assert progress.transition is None
    assert ("system", "Goblin Warrior moves down-left to (4, 3).") in progress.messages
    assert session.encounter_state.active_creature() == "player"
    assert session.encounter_state.round.number == 2


def test_archer_behavior_uses_ranged_weapon_without_closing_distance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()

    assert session.encounter_state is not None
    enemy = session.encounter_state.creatures["goblin_1"]
    enemy.behavior.type = "archer"
    initialize_action_selectors(session.encounter_state)
    session.encounter_state.creatures["goblin_2"].creature.current_health = 0
    session.encounter_state.creatures["goblin_3"].creature.current_health = 0
    enemy.position.x = 5
    enemy.position.y = 2
    session.encounter_state.active_position.x = 1
    session.encounter_state.active_position.y = 6
    session.encounter_state.turn.index = 1

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 20
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 4
    )

    progress = _ORCHESTRATOR.advance(session.encounter_state)

    attack_event = next(
        event
        for event in progress.events
        if event.type == "attack_resolved" and event.creature_ref == "goblin_1"
    )
    assert enemy.position.x == 5
    assert enemy.position.y == 2
    attack_roll_detail = _mapping(attack_event.data["attack_roll_detail"])
    assert attack_roll_detail["attack_type"] == "ranged"
    assert attack_roll_detail["weapon_name"] == "Shortbow"


def test_natural_one_is_an_automatic_miss_for_attack_rolls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()

    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    session.encounter_state.creatures[
        "goblin_1"
    ].creature.attributes.base_armor_class = 0
    starting_health = session.encounter_state.creatures[
        "goblin_1"
    ].creature.get_health()

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 1
    )

    attack_index = _action_id(session, "attack", "goblin_1")
    result = session.choose(attack_index)

    assert (
        "system",
        "Traveler misses Goblin Warrior (goblin_1).",
    ) in result.messages
    attack_event = next(
        event for event in result.events if event.type == "attack_resolved"
    )
    assert attack_event.data["hit"] is False
    assert attack_event.data["critical_hit"] is False
    assert attack_event.data["damage"] == 0
    assert attack_event.data["damage_roll_detail"] is None
    attack_roll_detail = _mapping(attack_event.data["attack_roll_detail"])
    assert attack_roll_detail["critical_miss"] is True
    assert (
        session.encounter_state.creatures["goblin_1"].creature.get_health()
        == starting_health
    )


def test_extra_attack_allows_second_attack_after_movement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()

    assert session.encounter_state is not None
    _active_creature(session).combat_profile.attacks_per_attack_action = 2
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    session.encounter_state.creatures["goblin_1"].creature.current_health = 20

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 20
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 1
    )

    attack_index = _action_id(session, "attack", "goblin_1")
    first_result = session.choose(attack_index)

    attack_events = [
        event for event in first_result.events if event.type == "attack_resolved"
    ]
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

    second_attack_events = [
        event for event in second_result.events if event.type == "attack_resolved"
    ]
    assert len(second_attack_events) == 1
    assert second_attack_events[0].data["attacks_remaining"] == 0
    assert session.encounter_state.creatures["goblin_1"].creature.get_health() == 10
    assert session.encounter_state.active_attacks_remaining == 0
    assert not any(
        label.startswith("Attack enemy") for label in _action_labels(session)
    )


def test_second_wind_appears_and_consumes_bonus_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    _active_creature(session).current_health = 10

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 5
    )

    second_wind_index = _action_id_by_label(session, "Second Wind")
    result = session.choose(second_wind_index)

    assert ("system", "Traveler uses Second Wind.") in result.messages
    assert ("system", "Healing: 1d10=5 + level 2 = 7; applied 7.") in result.messages
    assert _active_creature(session).get_health() == 17
    assert session.encounter_state is not None
    assert session.encounter_state.active_bonus_action_available is False
    assert _active_creature(session).feature_uses_remaining["second_wind"] == 1
    second_wind = next(
        action
        for action in session.read().action_options
        if action.label == "Second Wind"
    )
    assert second_wind.availability == "unavailable"
    assert second_wind.enabled is False
    event = next(event for event in result.events if event.type == "feature_used")
    assert event.data["feature_id"] == "second_wind"
    assert event.data["feature_name"] == "Second Wind"
    assert event.data["uses_remaining"] == 1
    healing_roll_detail = _mapping(event.data["healing_roll_detail"])
    assert healing_roll_detail["dice"] == "1d10"
    assert healing_roll_detail["applied_healing"] == 7


def test_second_wind_stays_visible_in_feature_column_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    _active_creature(session).current_health = 10

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 5
    )

    second_wind_index = _action_id_by_label(session, "Second Wind")
    session.choose(second_wind_index)

    presentation = build_session_presentation(observe_session(session))

    assert presentation.encounter is not None
    assert "Second Wind" in _action_labels(session)
    feature_actions = {
        action.label: action for action in presentation.encounter.feature_actions
    }
    assert set(feature_actions) == {"Second Wind", "Action Surge"}
    assert feature_actions["Second Wind"].enabled is False
    assert feature_actions["Second Wind"].reasons
    assert feature_actions["Second Wind"].cost["bonus_action"] == 1


def test_action_surge_grants_additional_action_for_same_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
    assert session.encounter_state is not None
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    session.encounter_state.creatures["goblin_1"].creature.current_health = 30

    def fixed_roll(sides: int) -> int:
        return 18 if sides == 20 else 6

    monkeypatch.setattr("srd_arena.domain.encounters.encounter.roll_die", fixed_roll)
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 6
    )

    first_attack_index = _action_id(session, "attack", "goblin_1")
    session.choose(first_attack_index)

    assert session.encounter_state.active_actions_remaining == 0

    action_surge_index = _action_id_by_label(session, "Action Surge")
    result = session.choose(action_surge_index)

    assert ("system", "Traveler uses Action Surge.") in result.messages
    assert session.encounter_state.active_actions_remaining == 1
    assert session.encounter_state.active_magic_actions_remaining == 0
    assert _active_creature(session).feature_uses_remaining["action_surge"] == 0
    assert any(action.kind == "attack" for action in session.read().action_options)
    assert not any(action.kind == "spell" for action in session.read().action_options)
    event = next(event for event in result.events if event.type == "feature_used")
    assert event.data["feature_id"] == "action_surge"
    assert event.data["granted_actions"] == 1

    second_attack = _action_id(session, "attack", "goblin_1")
    session.choose(second_attack)

    assert session.encounter_state.active_actions_remaining == 0


def test_presentation_surfaces_conditions_in_encounter_views(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()

    assert session.encounter_state is not None
    state = session.encounter_state
    state.active_position.x = 4
    state.active_position.y = 3
    state.creatures["goblin_1"].position.x = 4
    state.creatures["goblin_1"].position.y = 2
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 5
    )

    _choose_directional_spell(session, "Cast Color Spray", (4, 2))
    presentation = build_session_presentation(observe_session(session))

    assert presentation.encounter is not None
    assert "Blinded" in presentation.encounter.battlefield.summary_text
    assert presentation.encounter.resources.conditions == ()
    assert any(
        creature.creature_ref == "goblin_1" and creature.conditions == ("blinded",)
        for creature in presentation.encounter.battlefield.creatures
    )


def test_spell_actions_map_to_magic_menu_bucket() -> None:
    bucket = action_bucket(
        ActionObservation(
            id="spell-color_spray",
            label="Cast Color Spray",
            kind="spell",
            creature_ref="player",
            cost={"action": 1},
            source_id="color_spray",
        ),
    )

    assert bucket == "magic"


def test_grapple_actions_map_to_attack_menu_bucket() -> None:
    bucket = action_bucket(
        ActionObservation(
            id="player-grapple-0",
            label="Grapple enemy 1 (Goblin Warrior)",
            kind="grapple",
            creature_ref="player",
            cost={"action": 1},
        ),
    )

    assert bucket == "attack"


def test_grapple_actions_share_one_board_targeting_mode() -> None:
    actions = [
        ActionObservation(
            id=f"player-grapple-{index}",
            label=f"Grapple target {index}",
            kind="grapple",
            creature_ref="player",
            cost={"action": 1},
            target_ref=f"goblin_{index + 1}",
        )
        for index in range(2)
    ]

    modes = selection_modes(actions)

    mode = TargetSelectionMode(kind="grapple", source_trigger_id="grapple")
    assert set(modes) == {mode}
    assert set(modes[mode]) == {"goblin_1", "goblin_2"}
    assert mode_label(mode, actions) == "Grapple"


def test_attack_sources_have_distinct_board_targeting_modes() -> None:
    actions = [
        ActionObservation(
            id="goblin-scimitar-player",
            label="Scimitar player",
            kind="attack",
            creature_ref="goblin",
            cost={"action": 1},
            preferred_attack_name="Scimitar",
            target_ref="player",
        ),
        ActionObservation(
            id="goblin-shortbow-player",
            label="Shortbow player",
            kind="attack",
            creature_ref="goblin",
            cost={"action": 1},
            preferred_attack_name="Shortbow",
            target_ref="player",
        ),
    ]

    modes = selection_modes(actions)

    scimitar = TargetSelectionMode(kind="attack", source_trigger_id="Scimitar")
    shortbow = TargetSelectionMode(kind="attack", source_trigger_id="Shortbow")
    assert set(modes) == {scimitar, shortbow}
    assert modes[scimitar]["player"].preferred_attack_name == "Scimitar"
    assert modes[shortbow]["player"].preferred_attack_name == "Shortbow"
    assert mode_label(scimitar, actions) == "Scimitar"
    assert mode_label(shortbow, actions) == "Shortbow"


def test_unavailable_button_tooltip_lists_all_reasons() -> None:
    class Button:
        def __init__(self) -> None:
            self.enabled = True
            self.properties: dict[str, object] = {}
            self.tooltip = ""

        def setProperty(self, name: str, value: object) -> None:
            self.properties[name] = value

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = enabled

        def setToolTip(self, tooltip: str) -> None:
            self.tooltip = tooltip

    button = Button()
    actions = [
        ActionObservation(
            id="rend-target-1",
            label="Rend",
            kind="attack",
            creature_ref="dragon",
            enabled=False,
            availability="unavailable",
            reasons=(
                ActionReasonObservation("unavailable", "No Action remains."),
                ActionReasonObservation("unavailable", "The target is out of range."),
            ),
        ),
        ActionObservation(
            id="rend-target-2",
            label="Rend",
            kind="attack",
            creature_ref="dragon",
            enabled=False,
            availability="unavailable",
            reasons=(
                ActionReasonObservation("unavailable", "No Action remains."),
                ActionReasonObservation("unavailable", "The target is not available."),
            ),
        ),
    ]

    configure_action_button(type_cast(QPushButton, button), actions)

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
                ActionObservation(
                    id="attack-goblin",
                    label="Attack Goblin",
                    kind="attack",
                    creature_ref="player",
                    cost={"action": 1},
                    target_ref="goblin_1",
                )
            ],
            TargetSelectionMode(kind="attack", source_trigger_id="attack"),
        ),
        (0, [], None),
        (1, [], None),
    ],
)
def test_follow_up_attack_is_queued_only_with_attacks_and_targets(
    monkeypatch: pytest.MonkeyPatch,
    attacks_available: int,
    actions: list[ActionObservation],
    expected: TargetSelectionMode | None,
) -> None:
    window = GameWindow.__new__(GameWindow)
    window.presenter = type_cast(
        GamePresenter,
        SimpleNamespace(observation=object()),
    )
    presentation = SimpleNamespace(
        encounter=SimpleNamespace(
            resources=SimpleNamespace(attacks_available=attacks_available),
            non_movement_actions=actions,
        )
    )
    monkeypatch.setattr(
        "srd_arena.frontends.gui.app.build_session_presentation",
        lambda _session: presentation,
    )

    attack_mode = TargetSelectionMode(kind="attack", source_trigger_id="attack")
    assert GameWindow._available_follow_up_attack_mode(window, attack_mode) == expected


def test_clicking_actor_during_follow_up_attack_reopens_movement() -> None:
    attack_mode = TargetSelectionMode(
        kind="attack",
        source_trigger_id="Shortsword",
    )
    planned_for: list[str] = []
    window = type_cast(
        GameWindow,
        SimpleNamespace(
            presenter=SimpleNamespace(pending_target_mode=attack_mode),
            _presentation=SimpleNamespace(
                encounter=SimpleNamespace(non_movement_actions=[])
            ),
            _begin_movement_plan=planned_for.append,
        ),
    )

    GameWindow._handle_battlefield_creature_clicked(window, "assassin")

    assert planned_for == ["assassin"]


def test_allocation_target_clicks_add_and_shift_clicks_remove() -> None:
    mode = TargetSelectionMode(
        kind="toggle_spell_target",
        source_trigger_id="eldritch_blast",
    )
    presentation = SimpleNamespace(
        encounter=SimpleNamespace(
            non_movement_actions=[
                ActionObservation(
                    id="caster-spell-target-dummy-remove",
                    label="Remove Target Dummy (1)",
                    kind="toggle_spell_target",
                    creature_ref="caster",
                    source_trigger_id="eldritch_blast",
                    source_id="eldritch_blast",
                    target_ref="target_dummy",
                ),
                ActionObservation(
                    id="caster-spell-target-dummy-add",
                    label="Add Target Dummy (2)",
                    kind="toggle_spell_target",
                    creature_ref="caster",
                    source_trigger_id="eldritch_blast",
                    source_id="eldritch_blast",
                    target_ref="target_dummy",
                ),
            ]
        )
    )
    target_changes: list[tuple[str, bool, str | None]] = []
    window = type_cast(
        GameWindow,
        SimpleNamespace(
            _presentation=presentation,
            presenter=SimpleNamespace(
                pending_target_mode=mode,
                change_target=lambda target_ref, *, remove, source_trigger_id: (
                    target_changes.append((target_ref, remove, source_trigger_id))
                ),
            ),
            _handle_command_update=lambda update: update,
            _begin_movement_plan=lambda _creature_ref: None,
        ),
    )

    GameWindow._handle_battlefield_creature_clicked(
        window,
        "target_dummy",
    )
    GameWindow._handle_battlefield_creature_clicked(
        window,
        "target_dummy",
        remove_allocation=True,
    )

    assert target_changes == [
        ("target_dummy", False, "eldritch_blast"),
        ("target_dummy", True, "eldritch_blast"),
    ]


def test_exact_spell_allocation_auto_confirms_after_final_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(
        str(TACTICAL_SCENARIO_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    caster = _active_creature(session)
    assert caster.spellcasting is not None
    caster.attributes = replace(caster.attributes, level=5)
    caster.spellcasting.learned_spells.append(
        _build_referenced_spell(
            "Eldritch Blast", "XPHB", load_spell_catalog(SYSTEM_CONTENT_ROOT)
        )
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die",
        lambda sides: 15 if sides == 20 else 3,
    )
    initial = next(
        action
        for action in session.read().action_options
        if action.kind == "spell"
        and isinstance(action.details, SpellOptionDetails)
        and action.details.source_id == "eldritch_blast"
        and action.details.target_ref == "goblin_1"
    )
    session.choose(initial.id)
    assert state.interrupts.pending_spell_cast is not None
    add = next(
        action
        for action in session.read().action_options
        if action.kind == "toggle_spell_target"
        and isinstance(action.details, SpellOptionDetails)
        and action.details.target_ref == "goblin_1"
        and action.id.endswith("-add")
    )

    window = GameWindow.__new__(GameWindow)
    window.presenter = GamePresenter(RunningGame(session))
    window._presentation = build_session_presentation(window.presenter.observation)
    window.presenter.set_target_mode(
        TargetSelectionMode(
            kind="toggle_spell_target",
            source_trigger_id="eldritch_blast",
        )
    )
    window._action_menu_scope = ActionMenuScope("action", "magic")
    monkeypatch.setattr(window, "_apply_turn_result", lambda _result, **_kwargs: None)

    assert allocation_counts(window.presenter.observation) == {"goblin_1": 1}
    assert allocation_status(window.presenter.observation) == (
        "Eldritch Blast: 1 allocation remaining (1/2 assigned)"
    )

    GameWindow._select_action(window, add.id)

    assert state.interrupts.pending_spell_cast is None
    assert state.current_decision().kind == "turn"
    assert state.active_actions_remaining == 0


def test_movement_does_not_consume_pending_multiattack_slots() -> None:
    session = load_scenario_directory(
        str(STAT_BLOCK_ACTION_SCENARIO_DIR),
        start_scene="stat_block_action_showcase",
    ).create_session()
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    state.turn.index = state.initiative_order.index("assassin")
    actor = state.active_creature_state
    actor.movement_remaining = None
    actor.actions_remaining = 1
    actor.magic_actions_remaining = 1
    actor.attacks_remaining = 0
    actor.pending_multiattack.clear()

    multiattack = next(
        action for action in state.available_actions() if action.kind == "multiattack"
    )
    _ORCHESTRATOR.submit(state, multiattack)
    slots_before = tuple(actor.pending_multiattack)

    move = next(
        action
        for action in state.available_actions()
        if action.kind == "move" and action.value == "left"
    )
    _ORCHESTRATOR.submit(state, move)

    assert tuple(actor.pending_multiattack) == slots_before
    assert actor.attacks_remaining == len(slots_before)


def test_directional_spell_target_mode_stays_available_without_creature_target_map() -> (
    None
):
    pending_mode = TargetSelectionMode(
        kind="spell",
        source_trigger_id="color_spray",
    )
    actions = [
        ActionObservation(
            id="spell-color_spray",
            label="Cast Color Spray",
            kind="spell",
            creature_ref="player",
            cost={"action": 1},
            source_id="color_spray",
            area_preview={"shape": "cone"},
        )
    ]

    assert mode_is_available(actions, {}, pending_mode) is True


def test_spell_target_modes_preserve_selected_cast_level() -> None:
    actions = [
        ActionObservation(
            id=f"blight-{suffix}",
            label=label,
            kind="spell",
            creature_ref="spectrum_adept",
            cost={"action": 1},
            source_id="blight",
            resource_level=resource_level,
            target_ref="plant_target",
        )
        for suffix, label, resource_level in (
            ("base", "Cast Blight", None),
            ("level-5", "Cast Blight (Level 5)", 5),
            ("level-6", "Cast Blight (Level 6)", 6),
        )
    ]

    modes = selection_modes(actions)

    assert (
        modes[TargetSelectionMode(kind="spell", source_trigger_id="blight")][
            "plant_target"
        ].id
        == "blight-base"
    )
    assert (
        modes[
            TargetSelectionMode(
                kind="spell",
                source_trigger_id="blight",
                variant_id="Level 5",
            )
        ]["plant_target"].id
        == "blight-level-5"
    )
    assert (
        modes[
            TargetSelectionMode(
                kind="spell",
                source_trigger_id="blight",
                variant_id="Level 6",
            )
        ]["plant_target"].id
        == "blight-level-6"
    )


def test_goblin_encounter_attack_can_end_scene_with_victory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()

    assert session.encounter_state is not None
    _active_creature(session).combat_profile.attacks_per_attack_action = 1
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2
    session.encounter_state.creatures["goblin_1"].creature.current_health = 1
    session.encounter_state.creatures["goblin_2"].creature.current_health = 0
    session.encounter_state.creatures["goblin_3"].creature.current_health = 0

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 20
    )
    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_dice", lambda num_dice, sides: 4
    )

    attack_index = _action_id(session, "attack", "goblin_1")
    result = session.choose(attack_index)

    assert result.selected_choice_text is not None
    assert result.events[0].data["kind"] == "attack"
    assert session.current_scene_id == "goblin_encounter"
    assert session.pending_scene_transition is not None
    assert session.encounter_state is not None
    assert result.scene_changed is False
    assert session.read().action_options[0].id == "system-continue-scene-transition"


def test_attack_consumes_action_until_next_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()

    assert session.encounter_state is not None
    _active_creature(session).combat_profile.attacks_per_attack_action = 1
    session.encounter_state.active_position.x = 4
    session.encounter_state.active_position.y = 3
    session.encounter_state.creatures["goblin_1"].position.x = 4
    session.encounter_state.creatures["goblin_1"].position.y = 2

    monkeypatch.setattr(
        "srd_arena.domain.encounters.encounter.roll_die", lambda sides: 1
    )

    attack_index = _action_id(session, "attack", "goblin_1")
    session.choose(attack_index)

    assert session.encounter_state.active_action_available is False
    attacks = [
        action for action in session.read().action_options if action.kind == "attack"
    ]
    assert attacks
    assert all(action.availability == "unavailable" for action in attacks)

    wait_index = _action_id_by_label(session, "Wait")
    session.choose(wait_index)
    while session.encounter_state.current_decision().kind == "reaction":
        session.choose(_action_id_by_label(session, "Pass reaction"))

    assert session.encounter_state.creatures["player"].actions_remaining == 1
    assert any(action.kind == "attack" for action in session.read().action_options)


def test_encounter_victory_waits_for_continue_before_restart() -> None:
    session = load_scenario_directory(
        str(FIXTURE_ENCOUNTER_DIR), start_scene="goblin_encounter"
    ).create_session()
    session.read()
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
    scene = session.read()
    assert scene.scene_text == "Victory! Press continue to proceed."
    assert (
        session.pending_scene_transition.message
        == "Victory! Press continue to proceed."
    )
    assert scene.action_options[0].id == "system-continue-scene-transition"

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
