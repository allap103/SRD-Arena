from srd_arena.content.catalogs import (
    SourceCatalog,
    load_optional_feature_catalog,
)
from srd_arena.content.normalization import normalize_optional_feature_effects
from srd_arena.content.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.schemas import (
    OptionalFeatureFileSchema,
    OptionalFeatureSchema,
)


def test_bundled_optional_features_load_as_typed_records() -> None:
    catalog = load_optional_feature_catalog(SYSTEM_CONTENT_ROOT)

    fighting_style = catalog.find("Great Weapon Fighting", "PHB")

    assert len(catalog) >= 70
    assert isinstance(fighting_style, OptionalFeatureSchema)
    assert "FS:F" in fighting_style.feature_types


def test_optional_feature_schema_preserves_unknown_source_fields() -> None:
    [feature] = OptionalFeatureFileSchema.model_validate(
        {
            "optionalfeature": [
                {
                    "name": "Test Feature",
                    "source": "TEST",
                    "customFutureField": {"enabled": True},
                }
            ]
        }
    ).optional_features

    assert feature.model_extra == {"customFutureField": {"enabled": True}}


def test_optional_feature_normalization_builds_triggered_effect() -> None:
    catalog = load_optional_feature_catalog(SYSTEM_CONTENT_ROOT)

    [effect] = normalize_optional_feature_effects(
        catalog.find("Great Weapon Fighting", "PHB")
    )

    assert effect.id == "great_weapon_fighting"
    assert effect.trigger == "weapon_damage_rolled"
    assert effect.operation == "reroll_matching_dice"


def test_optional_feature_catalog_uses_srd_public_name() -> None:
    source_feature = OptionalFeatureSchema(
        name="Protected Feature",
        source="TEST",
        srd52="Public Feature",
    )
    catalog = SourceCatalog(
        [source_feature],
        name_of=lambda feature: feature.public_name,
        source_of=lambda feature: feature.source,
    )

    assert catalog.find("Public Feature", "TEST") is source_feature
