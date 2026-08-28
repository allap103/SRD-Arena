"""Reference authored class and subclass content from creature templates."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassRef:
    """Identify a class and the level a creature has reached in it."""

    name: str
    source: str | None = None


@dataclass(frozen=True)
class SubclassRef:
    """Identify the subclass selected for a creature's class progression."""

    name: str
    source: str | None = None
    class_name: str | None = None
    class_source: str | None = None
