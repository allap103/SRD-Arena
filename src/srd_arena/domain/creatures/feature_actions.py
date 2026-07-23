from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureActionDefinition:
    feature_id: str
    label: str
    economy: str
    target: str
    resolver: str
    combat_only: bool = True
