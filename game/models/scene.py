from dataclasses import dataclass, field

from .choice import Choice


@dataclass
class Scene:
    id: str
    text: str | None = None
    choices: list[Choice] = field(default_factory=list)
    type: str = "basic"

    def __str__(self):
        return f"Scene ID: {self.id}, Text: {self.text}, Choices: {[str(choice) for choice in self.choices]}"

    def __repr__(self):
        return f"Scene(id='{self.id}', text='{self.text}', choices={self.choices})"
