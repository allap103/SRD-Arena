from srd_arena.domain.creatures import Equipment
from srd_arena.domain.creatures import Inventory
from tests.helpers import make_creature


def test_equipping_moves_item_from_inventory_to_equipment() -> None:
    creature = make_creature()
    creature.inventory.add_item("greatsword")

    assert creature.equip_item("greatsword", "right_hand") is True
    assert creature.inventory.has_item("greatsword") is False
    assert creature.equipment.is_equipped("greatsword") is True


def test_invalid_equipment_slot_does_not_remove_inventory_item() -> None:
    creature = make_creature()
    creature.inventory.add_item("greatsword")

    assert creature.equip_item("greatsword", "invalid") is False
    assert creature.inventory.has_item("greatsword") is True


def test_unequipping_returns_item_to_inventory() -> None:
    creature = make_creature()
    creature.equipment.equip("greatsword", "right_hand")

    assert creature.unequip_item("right_hand") is True
    assert creature.inventory.has_item("greatsword") is True


def test_inventory_reports_removed_quantity() -> None:
    inventory = Inventory(items=["potion", "potion"])

    assert inventory.remove_items("potion", 3) == 2
    assert inventory.items == []


def test_equipment_show_returns_snapshot() -> None:
    equipment = Equipment()
    equipment.equip("greatsword", "right_hand")

    snapshot = equipment.show()
    snapshot["right_hand"] = None

    assert equipment.is_equipped("greatsword") is True
