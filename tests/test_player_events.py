from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent
from srd_arena.engine.player_events import PublicDamage, public_damage_from_event


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
