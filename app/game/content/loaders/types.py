from ..schemas import CreatureSchema

StatBlockCatalog = dict[tuple[str, str | None], dict]
ClassCatalog = dict[tuple[str, str | None], dict]
SubclassCatalog = dict[tuple[str, str | None, str | None, str | None], dict]
OptionalFeatureCatalog = dict[tuple[str, str | None], dict]
CustomStatBlockCatalog = dict[str, CreatureSchema]
SystemItemCatalog = dict[tuple[str, str | None], dict]
SpellCatalog = dict[tuple[str, str | None], dict]
