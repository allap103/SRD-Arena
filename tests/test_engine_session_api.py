from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.grappling_state import apply_grapple
from srd_arena.domain.rolls.randomness import DiceRoller
from srd_arena.engine.api import (
    AimAction,
    ConfirmTargeting,
    EncounterTerminationReason,
    GameObservation,
    SelectAction,
    Session,
    SetResourceAllocation,
)
from srd_arena.engine.session import PendingEncounterCompletion

FULL_CONTROL_ENCOUNTER_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "encounters"
    / "archive"
    / "full_control_showcase"
)
MASS_HEAL_ENCOUNTER_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "encounters"
    / "archive"
    / "mass_heal_allocation_showcase"
)
SPELL_DAMAGE_ENCOUNTER_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "encounters"
    / "archive"
    / "spell_damage_showcase"
)
STAT_BLOCK_ACTION_ENCOUNTER_DIR = (
    Path(__file__).parents[1]
    / "content"
    / "encounters"
    / "archive"
    / "stat_block_action_showcase"
)


def _session(encounter_id: str) -> Session:
    return Session(EncounterCatalog().load_encounter(encounter_id))


def _archived_id(encounter_directory: Path) -> str:
    return f"archive/{encounter_directory.name}"


def _advance_to_actor(
    session: Session,
    creature_ref: str,
) -> GameObservation:
    for _ in range(20):
        observation = session.observe()
        assert observation.encounter is not None
        if observation.encounter.decision.creature_ref == creature_ref:
            return observation
        if observation.requires_automatic_advance:
            session.advance_until_input_required()
            continue
        wait = next(
            action
            for action in observation.scene.action_details
            if action.kind == "wait" and action.enabled
        )
        result = session.execute(
            SelectAction(wait.id, observation.encounter.decision.id)
        )
        assert result.update is not None
    raise AssertionError(f"Creature '{creature_ref}' did not receive a turn.")


def test_session_exposes_frontend_neutral_observations_and_commands() -> None:
    session = _session(_archived_id(FULL_CONTROL_ENCOUNTER_DIR))
    observation = session.observe()
    assert observation.encounter is not None
    wait = next(
        action
        for action in observation.scene.action_details
        if action.kind == "wait" and action.enabled
    )

    result = session.execute(SelectAction(wait.id, observation.encounter.decision.id))
    next_observation = session.observe()

    assert observation.requires_automatic_advance is False
    assert observation.encounter.decision.creature_ref
    assert observation.encounter.creatures
    assert result.update is not None
    assert result.update.selected_action_id == wait.id
    assert next_observation.scene.scene_id == observation.scene.scene_id


def test_observation_exposes_combat_identity_defenses_and_resources() -> None:
    session = _session(_archived_id(FULL_CONTROL_ENCOUNTER_DIR))
    session.observe()
    assert session.encounter_state is not None
    player = session.encounter_state.creatures["player"].creature
    player.temporary_hit_points = 7
    player.statistics = replace(
        player.statistics,
        creature_type="humanoid",
        type_tags=("human",),
        condition_immunities=frozenset({Condition.FRIGHTENED}),
        damage_resistances=frozenset({"fire"}),
        damage_immunities=frozenset({"poison"}),
        damage_vulnerabilities=frozenset({"cold"}),
    )

    observation = session.observe()
    assert observation.encounter is not None
    observed_player = observation.encounter.creature("player")
    observed_goblin = observation.encounter.creature("red_blade")

    assert observed_player.temporary_hit_points == 7
    assert observed_player.creature_type == "humanoid"
    assert observed_player.type_tags == ("human",)
    assert observed_player.size == "M"
    assert observed_player.occupied_cells == (observed_player.position,)
    assert observed_player.defenses.condition_immunities == ("frightened",)
    assert observed_player.defenses.damage_resistances == ("fire",)
    assert observed_player.defenses.damage_immunities == ("poison",)
    assert observed_player.defenses.damage_vulnerabilities == ("cold",)
    assert {
        resource.id: (resource.remaining, resource.maximum)
        for resource in observed_player.resource_pools
    } == {
        "feature:action_surge": (1, 1),
        "feature:second_wind": (3, 3),
    }
    assert (observed_goblin.creature_type, observed_goblin.size) == ("fey", "S")

    player.temporary_hit_points = 0
    assert observed_player.temporary_hit_points == 7


def test_observation_exposes_stat_block_resources_and_relationships() -> None:
    session = _session(_archived_id(STAT_BLOCK_ACTION_ENCOUNTER_DIR))
    session.observe()
    assert session.encounter_state is not None
    state = session.encounter_state
    applied = build_applied_condition(
        condition=Condition.GRAPPLED,
        source_ref="blue_wyrmling",
        source_label="Stormscale",
        target_ref="breath_target_near",
        definition_id="test_grapple",
    )
    assert apply_grapple(state, applied).accepted is True

    observation = session.observe()
    assert observation.encounter is not None
    wyrmling = observation.encounter.creature("blue_wyrmling")

    assert len(wyrmling.resource_pools) == 1
    breath = wyrmling.resource_pools[0]
    assert (breath.kind, breath.remaining, breath.maximum) == ("recharge", 1, 1)
    assert (breath.refresh, breath.recharge_die_sides, breath.recharge_minimum) == (
        ("turn_start_recharge",),
        6,
        5,
    )
    assert len(observation.encounter.relationships) == 1
    relationship = observation.encounter.relationships[0]
    assert (
        relationship.kind,
        relationship.source_ref,
        relationship.target_ref,
        relationship.source_definition_id,
    ) == (
        "grappling",
        "blue_wyrmling",
        "breath_target_near",
        "test_grapple",
    )


def test_restart_rewinds_seeded_encounter_randomness() -> None:
    session = Session(
        EncounterCatalog().load_encounter(_archived_id(FULL_CONTROL_ENCOUNTER_DIR)),
        dice=DiceRoller.seeded(42),
    )
    session.observe()
    assert session.encounter_state is not None

    def random_signature() -> tuple[tuple[tuple[str, int], ...], tuple[int, ...]]:
        assert session.encounter_state is not None
        initiative = tuple(
            (entry.creature_ref, entry.roll)
            for entry in session.encounter_state.initiative_entries
        )
        following_rolls = tuple(
            session.encounter_state.dice.roll_die(sides) for sides in (20, 6, 8, 20)
        )
        return initiative, following_rolls

    first_run = random_signature()
    session.pending_encounter_completion = PendingEncounterCompletion(
        "Encounter complete"
    )

    result = session.choose("system-restart-encounter")

    assert result.selected_action_id == "system-restart-encounter"
    assert random_signature() == first_run


def test_reset_can_replace_and_then_replay_the_session_seed() -> None:
    encounter = EncounterCatalog().load_encounter(
        _archived_id(FULL_CONTROL_ENCOUNTER_DIR)
    )
    session = Session(encounter, seed=41)

    first_observation = session.observe()
    assert first_observation.encounter is not None
    assert session.seed == 41

    reseeded_observation = session.reset(seed=42)
    assert reseeded_observation.encounter is not None
    reseeded_initiative = reseeded_observation.encounter.initiative
    assert session.seed == 42

    replayed_observation = session.reset()
    assert replayed_observation.encounter is not None
    assert replayed_observation.encounter.initiative == reseeded_initiative
    assert session.seed == 42


def test_completion_without_survivors_reports_no_winner() -> None:
    session = _session(_archived_id(FULL_CONTROL_ENCOUNTER_DIR))
    session.observe()
    assert session.encounter_state is not None
    for creature_state in session.encounter_state.creatures.values():
        creature_state.creature.current_health = 0

    session._complete_encounter()
    completion = session.observe().completion

    assert completion is not None
    assert completion.reason is EncounterTerminationReason.ALL_TEAMS_DEFEATED
    assert completion.winning_team_id is None


def test_session_rejects_stale_commands_before_execution() -> None:
    session = _session(_archived_id(FULL_CONTROL_ENCOUNTER_DIR))
    observation = session.observe()
    assert observation.encounter is not None
    wait = next(
        action
        for action in observation.scene.action_details
        if action.kind == "wait" and action.enabled
    )

    result = session.execute(SelectAction(wait.id, "old-decision"))

    assert result.accepted is False
    assert result.failure is not None
    assert result.failure.code == "stale_decision"
    assert session.observe().encounter == observation.encounter


def test_session_aims_an_advertised_area_action() -> None:
    session = _session(_archived_id(SPELL_DAMAGE_ENCOUNTER_DIR))
    observation = _advance_to_actor(session, "spectrum_adept")
    assert observation.encounter is not None
    fireball = next(
        action
        for action in observation.scene.action_details
        if action.kind == "spell" and action.source_id == "fireball" and action.enabled
    )
    assert fireball.source_label == "Fireball"
    assert fireball.source_level == 3
    assert fireball.target_ref is None
    assert fireball.area_preview is not None
    assert fireball.area_preview["shape"] == "radius"
    assert not hasattr(fireball, "value")

    result = session.execute(
        AimAction(
            action_id=fireball.id,
            x=6.5,
            y=3.5,
            expected_decision_id=observation.encounter.decision.id,
        )
    )

    assert result.accepted is True
    assert result.update is not None
    assert result.update.selected_action_id == fireball.id


def test_session_controls_numeric_target_allocation() -> None:
    session = _session(_archived_id(MASS_HEAL_ENCOUNTER_DIR))
    observation = session.observe()
    assert observation.encounter is not None
    cast = next(
        action
        for action in observation.scene.action_details
        if action.kind == "spell" and action.enabled
    )
    started = session.execute(SelectAction(cast.id, observation.encounter.decision.id))
    assert started.update is not None
    targeting = started.update.observation.encounter
    assert targeting is not None and targeting.targeting is not None
    assert targeting.targeting.resource_pool_total == 700

    allocation = session.execute(
        SetResourceAllocation(
            target_ref="healer",
            amount=200,
            expected_decision_id=targeting.decision.id,
        )
    )
    assert allocation.update is not None
    allocated = allocation.update.observation.encounter
    assert allocated is not None and allocated.targeting is not None
    assert allocated.targeting.resource_allocations[0].amount == 200

    invalid = session.execute(
        SetResourceAllocation(
            target_ref="healer",
            amount=201,
            expected_decision_id=allocated.decision.id,
        )
    )
    assert invalid.failure is not None
    assert invalid.failure.code == "invalid_allocation"

    confirmed = session.execute(
        ConfirmTargeting(expected_decision_id=allocated.decision.id)
    )
    assert confirmed.accepted is True
