from srd_arena.content.common import SourceCatalog
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.equipment import ItemSchema, build_item, load_item_catalog


def test_bundled_items_load_as_typed_records() -> None:
    catalog = load_item_catalog(SYSTEM_CONTENT_ROOT)

    longbow = catalog.find("Longbow", "XPHB")

    assert len(catalog) == sum(
        len(list((SYSTEM_CONTENT_ROOT / directory).glob("*.json")))
        for directory in ("items_base", "items")
    )
    assert isinstance(longbow, ItemSchema)
    assert longbow.damage == "1d8"
    assert longbow.damage_type == "P"
    assert longbow.range == "150/600"


def test_item_schema_preserves_unknown_source_fields() -> None:
    item = ItemSchema.model_validate(
        {
            "name": "Test Item",
            "source": "TEST",
            "customFutureField": {"enabled": True},
        }
    )

    assert item.model_extra == {"customFutureField": {"enabled": True}}


def test_item_builder_creates_combat_ready_weapon() -> None:
    catalog = load_item_catalog(SYSTEM_CONTENT_ROOT)

    longbow = build_item(catalog.find("Longbow", "XPHB"))

    assert longbow.id == "longbow"
    assert longbow.category == "weapon"
    assert longbow.weapon_stat is not None
    assert longbow.weapon_stat.damage == "1d8"
    assert longbow.weapon_stat.damage_type == "piercing"
    assert longbow.weapon_stat.attack_type == "ranged"
    assert longbow.weapon_stat.range_normal == 150
    assert longbow.weapon_stat.range_long == 600


def test_item_builder_preserves_weapon_mastery_identity() -> None:
    """Carry the source-authored mastery property into the domain weapon."""

    catalog = load_item_catalog(SYSTEM_CONTENT_ROOT)

    maul = build_item(catalog.find("Maul", "XPHB"))
    javelin = build_item(catalog.find("Javelin", "XPHB"))

    assert maul.weapon_stat is not None
    assert javelin.weapon_stat is not None
    assert maul.weapon_stat.mastery == "Topple"
    assert javelin.weapon_stat.mastery == "Slow"


def test_item_builder_creates_typed_armor_statistics() -> None:
    """Preserve each armor category's AC formula and restrictions."""

    catalog = load_item_catalog(SYSTEM_CONTENT_ROOT)
    leather = build_item(catalog.find("Leather Armor", "XPHB"))
    hide = build_item(catalog.find("Hide Armor", "XPHB"))
    chain_mail = build_item(catalog.find("Chain Mail", "XPHB"))
    shield = build_item(catalog.find("Shield", "XPHB"))

    assert leather.armor_stat is not None
    assert leather.armor_stat.category == "light"
    assert leather.armor_stat.resolve_armor_class(3) == 14
    assert hide.armor_stat is not None
    assert hide.armor_stat.category == "medium"
    assert hide.armor_stat.resolve_armor_class(3) == 14
    assert chain_mail.armor_stat is not None
    assert chain_mail.armor_stat.category == "heavy"
    assert chain_mail.armor_stat.resolve_armor_class(3) == 16
    assert chain_mail.armor_stat.strength_requirement == 13
    assert chain_mail.armor_stat.stealth_disadvantage
    assert shield.armor_stat is not None
    assert shield.armor_stat.category == "shield"
    assert shield.armor_stat.armor_class == 2


def test_item_catalog_and_builder_use_srd_public_name() -> None:
    source_item = ItemSchema.model_validate(
        {
            "name": "Protected Item",
            "source": "TEST",
            "srd52": "Public Item",
        }
    )
    catalog = SourceCatalog(
        [source_item],
        name_of=lambda item: item.public_name,
        source_of=lambda item: item.source,
    )

    item = build_item(catalog.find("Public Item", "TEST"))

    assert item.id == "public_item"
    assert item.name == "Public Item"
