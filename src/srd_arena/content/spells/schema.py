from pydantic import Field, model_validator

from srd_arena.content.capabilities.schemas.authoring.declarations import (
    CapabilityDeclarationSchema,
)
from srd_arena.content.common.schema import SourceModel
from srd_arena.content.common.implementation import ImplementationSchema


class SpellSchema(SourceModel):
    """Validated view of the source fields used to build a spell."""

    name: str
    source: str
    level: int
    school: str
    time: list[dict[str, object]] = Field(default_factory=list)
    components: dict[str, object] = Field(default_factory=dict)
    duration: list[dict[str, object]] = Field(default_factory=list)
    implementation: ImplementationSchema = Field(default_factory=ImplementationSchema)
    capability: CapabilityDeclarationSchema | None = None
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @model_validator(mode="after")
    def validate_implementation_state(self) -> "SpellSchema":
        status = self.implementation.status
        if status in {"complete", "partial"} and self.capability is None:
            raise ValueError(f"{status.title()} spells must define a capability.")
        if (
            status in {"blocked", "unimplemented", "out_of_scope"}
            and self.capability is not None
        ):
            raise ValueError(f"{status.title()} spells cannot define a capability.")
        return self

    @property
    def executable(self) -> bool:
        return self.capability is not None and self.implementation.status in {
            "complete",
            "partial",
        }

    @property
    def public_name(self) -> str:
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name


class SpellFileSchema(SourceModel):
    """Container for spell records loaded from a source file."""

    spell: list[SpellSchema] = Field(default_factory=list)
