from srd_arena.domain.creatures import Attributes, Creature, Equipment, Inventory


def make_creature() -> Creature:
    return Creature(
        id="test-player",
        name="Test Player",
        description="",
        inventory=Inventory(),
        attributes=Attributes(
            base_health=10,
            level=1,
            strength=10,
            dexterity=10,
            constitution=14,
            wisdom=10,
            intelligence=10,
            charisma=10,
            base_armor_class=10,
        ),
        equipment=Equipment(),
    )
