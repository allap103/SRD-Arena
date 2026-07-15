from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleGrant:
    id: str
    source_type: str
    source_id: str
    trigger: str
    operation: str
    conditions: dict[str, object] = field(default_factory=dict)
    parameters: dict[str, object] = field(default_factory=dict)
