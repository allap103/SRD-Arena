class Inventory:
    def __init__(self):
        self.items = []

    def add_item(self, item: str):
        self.items.append(item)

    def remove_item(self, item: str):
        if item in self.items:
            self.items.remove(item)
        else:
            print(f"Item '{item}' not found in inventory.")

    def has_item(self, item: str) -> bool:
        return item in self.items
