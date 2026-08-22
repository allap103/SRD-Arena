from dataclasses import dataclass, field

from ..capabilities import CapabilityActivation, CapabilityDefinition


@dataclass(frozen=True)
class Spell:
    id: str
    name: str
    source: str | None
    level: int
    school: str | None = None
    components: dict[str, object] = field(default_factory=dict)
    concentration: bool = False
    definition: CapabilityDefinition | None = None
    activation: CapabilityActivation | None = None
