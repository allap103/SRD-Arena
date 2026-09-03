from srd_arena.content.character_options.classes import (
    OptionalFeatureSchema,
    load_optional_feature_catalog,
    normalize_optional_feature_effects,
)
from srd_arena.content.common import SourceCatalog
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT


def test_bundled_optional_features_load_as_typed_records() -> None:
    catalog = load_optional_feature_catalog(SYSTEM_CONTENT_ROOT)

    fighting_style = catalog.find("Great Weapon Fighting", "PHB")

    assert len(catalog) == len(
        list((SYSTEM_CONTENT_ROOT / "optional_features").glob("*.json"))
    )
    assert isinstance(fighting_style, OptionalFeatureSchema)
    assert "FS:F" in fighting_style.feature_types


def test_optional_feature_schema_preserves_unknown_source_fields() -> None:
    feature = OptionalFeatureSchema.model_validate(
        {
            "name": "Test Feature",
            "source": "TEST",
            "customFutureField": {"enabled": True},
        }
    )

    assert feature.model_extra == {"customFutureField": {"enabled": True}}


def test_optional_feature_normalization_builds_triggered_effect() -> None:
    catalog = load_optional_feature_catalog(SYSTEM_CONTENT_ROOT)

    [effect] = normalize_optional_feature_effects(
        catalog.find("Great Weapon Fighting", "PHB")
    )

    assert effect.id == "great_weapon_fighting"
    assert effect.trigger == "weapon_damage_rolled"
    assert effect.operation == "reroll_matching_dice"


def test_repelling_blast_normalizes_to_an_eldritch_blast_hit_trigger() -> None:
    catalog = load_optional_feature_catalog(SYSTEM_CONTENT_ROOT)

    [effect] = normalize_optional_feature_effects(
        catalog.find("Repelling Blast", "XPHB")
    )

    assert effect.id == "repelling_blast"
    assert effect.trigger == "spell_attack_hit"
    assert effect.operation == "push_away"
    assert effect.conditions == {"spell_id": "eldritch_blast"}
    assert effect.parameters == {
        "distance_feet": 10,
        "maximum_target_size": "L",
        "optional": True,
    }


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
