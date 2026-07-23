from ..schemas import CreatureSchema

ClassCatalog = dict[tuple[str, str | None], dict]
SubclassCatalog = dict[tuple[str, str | None, str | None, str | None], dict]
OptionalFeatureCatalog = dict[tuple[str, str | None], dict]
PlayerCharacterCatalog = dict[str, CreatureSchema]
SystemItemCatalog = dict[tuple[str, str | None], dict]
SpellCatalog = dict[tuple[str, str | None], dict]
