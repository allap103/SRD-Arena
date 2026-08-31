"""Attach loaded class-feature identity and descriptive metadata to creatures."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClassFeature:
    """Describe one class feature granted at a particular class level."""

    id: str
    name: str
    source_class: str
    level: int
    data: dict[str, object] = field(default_factory=dict)
