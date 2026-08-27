"""Provide feature actions support for the creatures package."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureActionDefinition:
    """Represent a feature action definition."""

    feature_id: str
    label: str
    economy: str
    target: str
    resolver: str
    combat_only: bool = True
