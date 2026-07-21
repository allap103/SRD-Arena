from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClassFeature:
    id: str
    name: str
    source_class: str
    level: int
    source_subclass: str | None = None
    data: dict[str, object] = field(default_factory=dict)
