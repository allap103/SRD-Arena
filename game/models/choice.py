from dataclasses import dataclass, field


@dataclass
class ItemRequirement:
    id: str
    quantity: int = 1
    missing_message: str | None = None
    consume: bool = False


@dataclass
class Requirements:
    items: list[ItemRequirement] = field(default_factory=list)


@dataclass
class Outcome:
    message: str | None = None
    gain_item: str | None = None
    lose_item: str | None = None
    damage: int = 0
    healing: int = 0


@dataclass
class Effects:
    on_success: Outcome | None = None
    on_failure: Outcome | None = None


@dataclass
class SkillTest:
    skill: str
    difficulty: int
    repeatable: bool = True
    effects: Effects | None = None


@dataclass
class Choice:
    choice_text: str
    next_scene: str | None
    message: str | None = None
    requirements: Requirements | None = None
    test: SkillTest | None = None
