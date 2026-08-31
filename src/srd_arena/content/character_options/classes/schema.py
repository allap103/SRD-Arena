"""Validate authored class and class-feature records."""

from pydantic import Field

from srd_arena.content.common.schema import SourceModel


class ClassFeatureReferenceSchema(SourceModel):
    """Define the authored character-option fields with class feature."""

    class_feature: str = Field(alias="classFeature")


class ClassTableGroupSchema(SourceModel):
    """Define the authored character-option fields with column labels and rows."""

    column_labels: list[object] = Field(default_factory=list, alias="colLabels")
    rows: list[list[object]] = Field(default_factory=list)
    spell_progression_rows: list[list[object]] = Field(
        default_factory=list,
        alias="rowsSpellProgression",
    )


class StartingProficienciesSchema(SourceModel):
    """Define the authored character-option fields with weapons."""

    weapons: list[object] = Field(default_factory=list)


class ClassFeatureSchema(SourceModel):
    """Define the authored character-option fields with name and source."""

    name: str
    source: str
    class_name: str = Field(alias="className")
    class_source: str = Field(alias="classSource")
    level: int
    entries: list[object] = Field(default_factory=list)
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @property
    def public_name(self) -> str:
        """Return the SRD-facing class-feature name.

        >>> feature = ClassFeatureSchema(name="Legacy", source="X", className="Fighter", classSource="X", level=1, srd52="Second Wind")
        >>> feature.public_name
        'Second Wind'
        """
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name


class ClassSchema(SourceModel):
    """Validate a class identity, progression table, and spellcasting metadata."""

    name: str
    source: str
    proficiency: list[str] = Field(default_factory=list)
    starting_proficiencies: StartingProficienciesSchema = Field(
        default_factory=StartingProficienciesSchema,
        alias="startingProficiencies",
    )
    class_features: list[str | ClassFeatureReferenceSchema] = Field(
        default_factory=list,
        alias="classFeatures",
    )
    table_groups: list[ClassTableGroupSchema] = Field(
        default_factory=list,
        alias="classTableGroups",
    )
    spellcasting_ability: str | None = Field(
        default=None,
        alias="spellcastingAbility",
    )
    caster_progression: str | None = Field(
        default=None,
        alias="casterProgression",
    )
    cantrip_progression: list[object] = Field(
        default_factory=list,
        alias="cantripProgression",
    )
    spells_known_progression: list[object] = Field(
        default_factory=list,
        alias="spellsKnownProgression",
    )
    srd: bool | str | None = None
    srd52: bool | str | None = None

    @property
    def public_name(self) -> str:
        """Return the SRD-facing class name.

        >>> ClassSchema(name="Fighter Legacy", source="X", srd52="Fighter").public_name
        'Fighter'
        """
        for marker in (self.srd52, self.srd):
            if isinstance(marker, str):
                return marker
        return self.name


class ClassFileSchema(SourceModel):
    """Define the authored class and class-feature records."""

    classes: list[ClassSchema] = Field(default_factory=list, alias="class")
    class_features: list[ClassFeatureSchema] = Field(
        default_factory=list,
        alias="classFeature",
    )
