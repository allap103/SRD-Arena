from dataclasses import dataclass


@dataclass
class Choice:
    choice_text: str
    next_scene: str | None
    data: dict | None = None
