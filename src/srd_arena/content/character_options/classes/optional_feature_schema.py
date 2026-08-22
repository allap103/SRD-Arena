from srd_arena.content.common.schema import SourceModel


class OptionalFeatureSchema(SourceModel):
    name: str
    source: str
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @property
    def public_name(self) -> str:
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name
