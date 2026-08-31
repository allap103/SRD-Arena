"""Reference authored class content from creature templates."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassRef:
    """Identify a class and the level a creature has reached in it."""

    name: str
    source: str | None = None
