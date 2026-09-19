"""Verify the Zombie's Slam, defenses, and Undead Fortitude lifecycle."""

from collections.abc import Iterable

from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.domain.capabilities import DamageEffect
from srd_arena.domain.creatures import AttackActionDefinition, Creature
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.rule_effects import DamageTriggeredDefeatSave
from srd_arena.domain.encounters.actions.creature_actions.discovery import (
    available_creature_actions,
)
from srd_arena.domain.encounters.actions.stat_block_runtime.validation import (
    stat_block_action_runtime_issue,
)
from srd_arena.domain.encounters.creature_control import execute_creature_action
from srd_arena.domain.encounters.defeat import resolve_creature_defeat
from srd_arena.domain.encounters.definitions import (
    EncounterBehavior,
    EncounterDefinition,
    EncounterTeam,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.encounters.state_combat import apply_combat_damage
from srd_arena.domain.geometry import Grid, Position
from srd_arena.domain.rolls.randomness import DiceRoller

BESTIARY = load_bestiary_catalog(SYSTEM_CONTENT_ROOT)


def _monster(creature_id: str, name: str) -> Creature:
    return build_creature(
        CreatureSchema.model_validate(
            {
                "id": creature_id,
                "stat_block": {"name": name, "source": "XMM"},
            }
        ),
        bestiary=BESTIARY,
    )


def _encounter(
    rolls: Iterable[int],
    *,
    zombie_health: int = 4,
) -> EncounterState:
    resolved_rolls = iter(rolls)
    zombie = _monster("zombie", "Zombie")
    zombie.current_health = zombie_health
    behavior = EncounterBehavior(type="wait")
    return EncounterState(
        "zombie-test",
        EncounterDefinition(
            "zombie-test",
            Grid(8, 8),
            teams=[
                EncounterTeam("attackers", "Attackers", ["skeleton"], "external"),
                EncounterTeam("undead", "Undead", ["zombie"], "external"),
            ],
        ),
        {
            "skeleton": EncounterCreatureState(
                "skeleton",
                _monster("skeleton", "Skeleton"),
                Position(1, 1),
                behavior,
            ),
            "zombie": EncounterCreatureState(
                "zombie",
                zombie,
                Position(2, 1),
                behavior,
            ),
        },
        initiative_order=["skeleton", "zombie"],
        dice=DiceRoller(die_roller=lambda _sides: next(resolved_rolls)),
    )


def _shortsword_attack(state: EncounterState) -> EncounterProgress:
    action = next(
        action
        for action in available_creature_actions(state, "skeleton")
        if action.kind == "attack"
        and action.value == "zombie"
        and action.preferred_attack_name == "Shortsword"
    )
    return execute_creature_action(
        state,
        action,
        state.current_decision(),
    ).progress


def test_zombie_loads_complete_core_combat_rules() -> None:
    zombie = _monster("zombie", "Zombie")

    assert zombie.size == "M"
    assert zombie.attributes.movement.speed_feet == 20
    assert zombie.statistics.creature_type == "undead"
    assert zombie.sense_range("darkvision") == 60
    assert zombie.statistics.damage_immunities == frozenset({"poison"})
    assert zombie.statistics.condition_immunities == frozenset(
        {Condition.EXHAUSTION, Condition.POISONED}
    )

    slam = zombie.stat_block_actions["Slam"]
    assert isinstance(slam, AttackActionDefinition)
    assert slam.attack_modes == ("melee",)
    assert slam.attack_bonus == 3
    assert slam.reach_feet == 5
    assert slam.hit == (DamageEffect("1d8", 1, "bludgeoning"),)
    assert stat_block_action_runtime_issue(slam) is None

    provider = zombie.combat_profile.intrinsic_rule_providers["undead_fortitude"]
    assert provider.label == "Undead Fortitude"
    assert provider.rule_effects == (
        DamageTriggeredDefeatSave(
            ability="constitution",
            base_dc=5,
            bypass_damage_types=frozenset({"radiant"}),
            bypass_critical_hits=True,
        ),
    )


def test_undead_fortitude_success_restores_one_hit_point() -> None:
    state = _encounter([19, 1, 10])

    progress = _shortsword_attack(state)

    zombie = state.creatures["zombie"].creature
    assert zombie.get_health() == 1
    assert "zombie" not in state.defeated_creature_refs
    assert state.pending_lethal_damage == {}
    event = next(
        event
        for event in progress.events
        if event.type == "feature_triggered"
        and event.data["feature_id"] == "undead_fortitude"
    )
    assert event.data["damage"] == 4
    assert event.data["save_dc"] == 9
    assert event.data["save_total"] == 13
    assert event.data["prevented_defeat"] is True
    assert not any(message == "Zombie is defeated." for _, message in progress.messages)


def test_failed_undead_fortitude_save_finalizes_defeat() -> None:
    state = _encounter([19, 1, 1])

    progress = _shortsword_attack(state)

    assert state.creatures["zombie"].creature.get_health() == 0
    assert "zombie" in state.defeated_creature_refs
    assert state.pending_lethal_damage == {}
    assert [
        event.type
        for event in progress.events
        if event.type in {"feature_triggered", "creature_defeated"}
    ] == ["feature_triggered", "creature_defeated"]
    assert ("system", "Zombie is defeated.") in progress.messages


def test_critical_hit_bypasses_undead_fortitude() -> None:
    state = _encounter([20, 1, 1])

    progress = _shortsword_attack(state)

    assert "zombie" in state.defeated_creature_refs
    assert not any(
        event.type == "feature_triggered"
        and event.data.get("feature_id") == "undead_fortitude"
        for event in progress.events
    )


def test_radiant_damage_bypasses_undead_fortitude() -> None:
    state = _encounter([])
    apply_combat_damage(state, "zombie", 4, "radiant")
    progress = EncounterProgress()

    resolve_creature_defeat(
        state,
        "zombie",
        defeated_by_ref="skeleton",
        progress=progress,
    )

    assert "zombie" in state.defeated_creature_refs
    assert [event.type for event in progress.events] == ["creature_defeated"]


def test_undead_fortitude_dc_uses_uncapped_damage_taken() -> None:
    state = _encounter([4], zombie_health=1)
    apply_combat_damage(state, "zombie", 8, "bludgeoning")
    progress = EncounterProgress()

    resolve_creature_defeat(
        state,
        "zombie",
        defeated_by_ref="skeleton",
        progress=progress,
    )

    event = next(
        event
        for event in progress.events
        if event.type == "feature_triggered"
        and event.data["feature_id"] == "undead_fortitude"
    )
    assert event.data["damage"] == 8
    assert event.data["save_dc"] == 13
    assert event.data["success"] is False


def test_undead_fortitude_combines_one_damage_occurrence_before_rolling() -> None:
    state = _encounter([10])
    apply_combat_damage(state, "zombie", 4, "force")
    apply_combat_damage(state, "zombie", 3, "necrotic")
    progress = EncounterProgress()

    resolve_creature_defeat(
        state,
        "zombie",
        defeated_by_ref="skeleton",
        progress=progress,
    )

    event = next(
        event
        for event in progress.events
        if event.type == "feature_triggered"
        and event.data["feature_id"] == "undead_fortitude"
    )
    assert event.data["damage"] == 7
    assert event.data["damage_types"] == ["force", "necrotic"]
    assert event.data["save_dc"] == 12
    assert event.data["success"] is True
    assert state.creatures["zombie"].creature.get_health() == 1
