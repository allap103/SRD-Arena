from typing import Literal

from pydantic import Field, model_validator

from .base import SpellCapabilitySchemaModel

ImplementationScope = Literal["combat", "exploration", "social", "world"]


def _default_implementation_scope() -> list[ImplementationScope]:
    return ["combat"]


class ImplementationOmissionSchema(SpellCapabilitySchemaModel):
    mechanic: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SpellImplementationSchema(SpellCapabilitySchemaModel):
    status: Literal[
        "complete",
        "partial",
        "unimplemented",
        "blocked",
        "out_of_scope",
    ] = "unimplemented"
    scope: list[ImplementationScope] = Field(
        default_factory=_default_implementation_scope
    )
    omissions: list[ImplementationOmissionSchema] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    reason: str | None = None
    resolver: Literal["slow"] | None = None

    @model_validator(mode="after")
    def validate_status_details(self) -> SpellImplementationSchema:
        if self.status == "partial" and not self.omissions:
            raise ValueError("Partial spell implementations must list omissions.")
        if self.status == "blocked" and not self.blocked_by:
            raise ValueError("Blocked spell implementations must list blockers.")
        if self.status == "out_of_scope" and not self.reason:
            raise ValueError("Out-of-scope spells must provide a reason.")
        if self.status == "complete" and (self.omissions or self.blocked_by):
            raise ValueError("Complete spell implementations cannot have omissions.")
        if self.status in {"unimplemented", "blocked", "out_of_scope"} and (
            self.resolver is not None
        ):
            raise ValueError(
                f"{self.status.title()} spells cannot register a custom resolver."
            )
        return self
