from ..models.item import Item


class Equipment:
    head: Item
    body: Item
    legs: Item
    feet: Item
    hands: Item
    right_hand: Item
    left_hand: Item
    accessory: Item

    def __init__(self, head: Item = None, body: Item = None, legs: Item = None, feet: Item = None, hands: Item = None, right_hand: Item = None, left_hand: Item = None, accessory: Item = None):
        self.head = head
        self.body = body
        self.legs = legs
        self.feet = feet
        self.hands = hands
        self.right_hand = right_hand
        self.left_hand = left_hand
        self.accessory = accessory

    def equip(self, item: str, slot: str):
        """
        Equips an item. If the slot is not empty, unequip the currently equipped item first.
         - item: The name of the item to equip.
         - slot: The equipment slot to equip the item in (e.g., 'head', 'body', 'right_hand').
        """
        if slot not in self.equipped_items:
            print(f"Invalid equipment slot '{slot}'.")
            return
        elif self.equipped_items[slot] is not None:
            self.unequip(slot)
        self.equipped_items[slot] = item
        print(f"Equipped '{item}' in slot '{slot}'.")

    def unequip(self, slot: str):
        if slot not in self.equipped_items:
            print(f"Invalid equipment slot '{slot}'.")
            return
        if self.equipped_items[slot] is not None:
            removed_item = self.equipped_items.pop(slot)
            print(f"Unequipped '{removed_item}' from slot '{slot}'.")
        else:
            print(f"No item equipped in slot '{slot}' to unequip.")

    def show(self):
        print("Equipped items:")
        for slot, item in self.equipped_items.items():
            if item is not None:
                print(f"{slot.capitalize()}: {item}")
            else:
                print(f"{slot.capitalize()}: Empty")
