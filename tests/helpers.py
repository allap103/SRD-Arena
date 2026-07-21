from srd_arena.domain.creatures import Creature
from srd_arena.domain.creatures import Attributes
from srd_arena.domain.creatures import Equipment
from srd_arena.domain.creatures import Inventory


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
