"""Provide classes support for the creatures package."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassRef:
    """Represent a class ref."""

    name: str
    source: str | None = None


@dataclass(frozen=True)
class SubclassRef:
    """Represent a subclass ref."""

    name: str
    source: str | None = None
    class_name: str | None = None
    class_source: str | None = None
