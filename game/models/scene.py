import json

from .choice import Choice


class Scene:
    id: str
    text: str
    choices: list[Choice]

    def __init__(self, id, text: str = None, choices: list[Choice] = None):
        self.id = id
        self.text = text
        self.choices = choices

    def __str__(self):
        return f"Scene ID: {self.id}, Text: {self.text}, Choices: {[str(choice) for choice in self.choices]}"

    def __repr__(self):
        return f"Scene(id='{self.id}', text='{self.text}', choices={self.choices})"

    def display(self):
        print(self.text)
        for i, choice in enumerate(self.choices):
            print(f"{i + 1}. {choice.choice_text}")

    def run(self):
        self.display()
        choice = input("Input a number: ")
        print(f"You chose: {choice}")
        try:
            choice_index = int(choice) - 1
            if 0 <= choice_index < len(self.choices):
                next_id = self.choices[choice_index].next_scene
                return next_id
            else:
                print("Invalid choice. Please try again.")
                return self.run()
        except ValueError:
            print("Invalid input. Please enter a valid number.")
            return self.run()

    @classmethod
    def from_dict(cls, data: dict):
        choices = []
        for text, choice_data in data.get("choices", {}).items():
            if isinstance(choice_data, dict):
                choices.append(
                    Choice(
                        choice_text=text,
                        next_scene=choice_data.get("next_scene"),
                        data=choice_data,
                    )
                )
                continue

            raise TypeError(
                f"Choice '{text}' must be an object with at least a 'next_scene' field; "
                f"got {type(choice_data).__name__}."
            )

        return cls(
            id=data.get("id"),
            text=data.get("text"),
            choices=choices,
        )

    @classmethod
    def from_file(cls, path):
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)
