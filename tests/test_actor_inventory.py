from game.domain.equipment import Equipment
from game.domain.inventory import Inventory
from tests.helpers import make_actor


def test_equipping_moves_item_from_inventory_to_equipment() -> None:
    actor = make_actor()
    actor.inventory.add_item("greatsword")

    assert actor.equip_item("greatsword", "right_hand") is True
    assert actor.inventory.has_item("greatsword") is False
    assert actor.equipment.is_equipped("greatsword") is True


def test_invalid_equipment_slot_does_not_remove_inventory_item() -> None:
    actor = make_actor()
    actor.inventory.add_item("greatsword")

    assert actor.equip_item("greatsword", "invalid") is False
    assert actor.inventory.has_item("greatsword") is True


def test_unequipping_returns_item_to_inventory() -> None:
    actor = make_actor()
    actor.equipment.equip("greatsword", "right_hand")

    assert actor.unequip_item("right_hand") is True
    assert actor.inventory.has_item("greatsword") is True


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
