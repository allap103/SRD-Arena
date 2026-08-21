from srd_arena.content.classes import load_class_catalog, load_subclass_catalog
from srd_arena.content.common import SourceCatalog
from srd_arena.content.classes import ClassRecord, ClassSchema
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT


def test_bundled_classes_load_with_typed_feature_records() -> None:
    catalog = load_class_catalog(SYSTEM_CONTENT_ROOT)

    fighter = catalog.find("Fighter", "XPHB")

    assert len(catalog) == 12
    assert isinstance(fighter.definition, ClassSchema)
    assert fighter.definition.proficiency == ["str", "con"]
    assert any(feature.public_name == "Second Wind" for feature in fighter.features)


def test_bundled_subclasses_use_class_aware_identity() -> None:
    catalog = load_subclass_catalog(SYSTEM_CONTENT_ROOT)

    champion = catalog.find("Champion", "XPHB", "Fighter", "XPHB")

    assert len(catalog) == 24
    assert champion.definition.class_name == "Fighter"
    assert any(feature.public_name == "Improved Critical" for feature in champion.features)


def test_class_schema_preserves_unknown_source_fields() -> None:
    class_definition = ClassSchema.model_validate(
        {
            "name": "Test Class",
            "source": "TEST",
            "customFutureField": {"enabled": True},
        }
    )

    assert class_definition.model_extra == {
        "customFutureField": {"enabled": True}
    }


def test_class_catalog_uses_srd_public_name() -> None:
    definition = ClassSchema(
        name="Protected Class",
        source="TEST",
        srd52="Public Class",
    )
    record = ClassRecord(definition=definition, features=())
    catalog = SourceCatalog(
        [record],
        name_of=lambda value: value.definition.public_name,
        source_of=lambda value: value.definition.source,
    )

    assert catalog.find("Public Class", "TEST") is record
