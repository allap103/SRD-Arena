from dataclasses import dataclass


@dataclass(frozen=True)
class ClassRef:
    name: str
    source: str | None = None


@dataclass(frozen=True)
class SubclassRef:
    name: str
    source: str | None = None
    class_name: str | None = None
    class_source: str | None = None
