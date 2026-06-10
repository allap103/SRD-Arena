from game.models.actor import Actor
from game.models.attributes import Attributes
from game.systems.equipment import Equipment
from game.systems.inventory import Inventory


def make_actor() -> Actor:
    return Actor(
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
