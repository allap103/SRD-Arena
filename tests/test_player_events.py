from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent
from srd_arena.engine.player_events import (
    PublicDamage,
    public_damage_from_event,
    public_events_from_event,
)
from srd_arena.engine.player_observation_models import PublicEventKind


def test_public_damage_supports_attack_and_spell_event_shapes() -> None:
    attack = CombatEvent(
        1,
        "attack_resolved",
        data={"target_ref": "goblin", "damage": 7},
    )
    spell = CombatEvent(
        2,
        "spell_cast",
        data={
            "damage_roll_details": [
                {"target_ref": "goblin", "applied_damage": 8},
                {"target_ref": "ogre", "applied_damage": 4},
            ]
        },
    )

    assert public_damage_from_event(attack) == (PublicDamage("goblin", 7),)
    assert public_damage_from_event(spell) == (
        PublicDamage("goblin", 8),
        PublicDamage("ogre", 4),
    )


def test_public_damage_supports_stat_block_and_retaliation_events() -> None:
    stat_block = CombatEvent(
        1,
        "stat_block_action_resolved",
        data={
            "outcomes": [
                {"target_ref": "hero", "damage": 9},
                {"target_ref": "ally", "damage": 4},
            ]
        },
    )
    retaliation = CombatEvent(
        2,
        "attack_hit_retaliation",
        data={"attacker_ref": "goblin", "damage": 5},
    )

    assert public_damage_from_event(stat_block) == (
        PublicDamage("hero", 9),
        PublicDamage("ally", 4),
    )
    assert public_damage_from_event(retaliation) == (PublicDamage("goblin", 5),)


def test_public_damage_ignores_non_damage_and_zero_damage() -> None:
    assert public_damage_from_event(CombatEvent(1, "turn_started")) == ()
    assert (
        public_damage_from_event(
            CombatEvent(
                2,
                "attack_resolved",
                data={"target_ref": "goblin", "damage": 0},
            )
        )
        == ()
    )


def test_public_attack_event_redacts_an_unseen_attacker_and_private_rolls() -> None:
    event = CombatEvent(
        1,
        "attack_resolved",
        creature_ref="hidden_archer",
        data={
            "target_ref": "warlock",
            "attack_name": "Longbow",
            "attack_roll": 27,
            "attack_roll_detail": {"modifier": 12},
            "hit": True,
            "damage": 8,
        },
    )

    [projected] = public_events_from_event(
        event,
        visible_creature_refs=frozenset({"warlock"}),
    )

    assert projected.kind is PublicEventKind.ATTACK
    assert projected.actor_ref is None
    assert projected.target_ref == "warlock"
    assert projected.source_id is None
    assert projected.outcome == "hit"
    assert projected.amount == 8
    assert not hasattr(projected, "data")


def test_public_events_record_visible_spell_and_stat_block_sources() -> None:
    spell = CombatEvent(
        2,
        "spell_cast",
        creature_ref="mage",
        data={
            "spell_id": "fireball",
            "target_refs": ["warlock"],
            "save_details": [{"modifier": 99, "target_dc": 30}],
            "damage_roll_details": [{"target_ref": "warlock", "applied_damage": 14}],
        },
    )
    breath = CombatEvent(
        3,
        "stat_block_action_resolved",
        creature_ref="dragon",
        data={
            "action_name": "Fire Breath",
            "outcomes": [{"target_ref": "warlock", "success": False, "damage": 21}],
        },
    )
    visible = frozenset({"mage", "dragon", "warlock"})

    [spell_event] = public_events_from_event(
        spell,
        visible_creature_refs=visible,
    )
    [breath_event] = public_events_from_event(
        breath,
        visible_creature_refs=visible,
    )

    assert spell_event.source_id == "spell:fireball"
    assert spell_event.amount == 14
    assert breath_event.source_id == "stat_block:fire_breath"
    assert breath_event.outcome == "save_failed"


def test_only_obvious_condition_events_are_public() -> None:
    prone = CombatEvent(
        4,
        "condition_applied",
        creature_ref="goblin",
        data={"condition": "prone"},
    )
    poisoned = CombatEvent(
        5,
        "condition_applied",
        creature_ref="goblin",
        data={"condition": "poisoned"},
    )

    [public_prone] = public_events_from_event(
        prone,
        visible_creature_refs=frozenset({"goblin"}),
    )

    assert public_prone.kind is PublicEventKind.CONDITION
    assert public_prone.source_id == "condition:prone"
    assert (
        public_events_from_event(
            poisoned,
            visible_creature_refs=frozenset({"goblin"}),
        )
        == ()
    )
