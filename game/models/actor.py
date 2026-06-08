from ..systems.equipment import Equipment
from ..systems.inventory import Inventory
from .attributes import Attributes


class Actor:
    inventory: Inventory
    attributes: Attributes
    equipment: Equipment

    def __init__(self, inventory: Inventory, attributes: Attributes, equipment: Equipment):
        self.inventory = inventory
        self.attributes = attributes
        self.equipment = equipment

    def __str__(self):
        return f"Actor with attributes: {self.attributes} and inventory: {self.inventory.items}"

    @classmethod
    def from_dict(cls, data: dict):
        inventory = Inventory()
        for item in data.get("inventory", []):
            inventory.add_item(item)

        attributes_data = data.get("attributes", {})
        attributes = Attributes(
            base_health=attributes_data.get("base_health", 10),
            level=attributes_data.get("level", 1),
            strength=attributes_data.get("strength", 10),
            dexterity=attributes_data.get("dexterity", 10),
            constitution=attributes_data.get("constitution", 10),
            wisdom=attributes_data.get("wisdom", 10),
            intelligence=attributes_data.get("intelligence", 10),
            charisma=attributes_data.get("charisma", 10),
            base_armor_class=attributes_data.get("base_armor_class", 10),
        )

        equipment = Equipment()
        for item in data.get("equipment", []):
            equipment.equip(item)

        return cls(inventory, attributes, equipment)

    def has_item(self, item: str) -> bool:
        return self.inventory.has_item(item)

    def add_item(self, item: str):
        self.inventory.add_item(item)

    def remove_item(self, item: str):
        self.inventory.remove_item(item)

    def show_equipment(self):
        self.equipment.show()

    def equip_item(self, item: str):
        if self.inventory.has_item(item):
            self.equipment.equip(item)
            self.inventory.remove_item(item)
        else:
            print(f"Item '{item}' not found in inventory.")

    def unequip_item(self, item: str):
        if self.equipment.is_equipped(item):
            self.equipment.unequip(item)
            self.inventory.add_item(item)
        else:
            print(f"Item '{item}' is not currently equipped.")

    def get_modifier(self, attribute_value: int) -> int:
        return (attribute_value - 10) // 2

    def get_health(self) -> int:
        return self.attributes.base_health + self.get_modifier(self.attributes.constitution) * self.attributes.level

    def get_armor_class(self) -> int:
        return self.attributes.base_armor_class + self.get_modifier(self.attributes.dexterity)
