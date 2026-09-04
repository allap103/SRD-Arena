"""Assemble creature domain templates from validated authored records."""

from pathlib import Path
from typing import cast

from srd_arena.content.character_options.classes import (
    ClassCatalog,
    OptionalFeatureCatalog,
)
from srd_arena.content.common.sources import load_json, slug
from srd_arena.content.spells import SpellCatalog
from srd_arena.domain.creatures import (
    ClassRef,
    Creature,
    Equipment,
    Inventory,
)
from srd_arena.domain.creatures.feature_rules import (
    LUCKY_FEATURE_ID,
    feat_triggered_effects,
)

from .actions.builder import (
    build_declared_stat_block_actions,
    build_stat_block_actions,
)
from .actions.multiattack import MultiattackCapabilitySchema, build_multiattack
from .attributes import build_creature_attributes, build_creature_size
from .catalog import BestiaryCatalog
from .character_options import (
    find_class_record,
    resolve_class_features,
    resolve_optional_feature_effects,
)
from .character_snapshots import CharacterSnapshotCatalog, build_character_profile
from .features import build_combat_profile, build_feature_uses_remaining
from .player_characters import PlayerCharacterTemplates
from .schema import CreatureItemReferenceSchema, CreatureSchema
from .spellcasting import build_spellcasting
from .stat_block_schema import BestiaryMonsterSchema
from .statistics import build_creature_statistics


def load_creature(
    path: str | Path,
    bestiary: BestiaryCatalog | None = None,
    classes: ClassCatalog | None = None,
    player_characters: PlayerCharacterTemplates | None = None,
    optional_features: OptionalFeatureCatalog | None = None,
    spells: SpellCatalog | None = None,
    character_snapshots: CharacterSnapshotCatalog | None = None,
) -> Creature:
    """Validate one creature document and translate it with the supplied catalogs.

    >>> from pathlib import Path
    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     path = Path(directory) / "hero.json"
    ...     _ = path.write_text('{"id": "hero", "name": "Hero"}')
    ...     creature = load_creature(path)
    >>> (creature.id, creature.name)
    ('hero', 'Hero')
    """

    return build_creature(
        CreatureSchema.model_validate(load_json(path)),
        bestiary,
        classes,
        player_characters,
        optional_features,
        spells,
        character_snapshots,
    )


def build_creature(
    schema: CreatureSchema,
    bestiary: BestiaryCatalog | None = None,
    classes: ClassCatalog | None = None,
    player_characters: PlayerCharacterTemplates | None = None,
    optional_features: OptionalFeatureCatalog | None = None,
    spells: SpellCatalog | None = None,
    character_snapshots: CharacterSnapshotCatalog | None = None,
) -> Creature:
    """Assemble a domain creature from authored statistics, actions, and options.

    >>> creature = build_creature(CreatureSchema(id="hero", name="Hero"))
    >>> (creature.id, creature.attributes.base_health)
    ('hero', 10)
    """

    schema = _resolve_creature_schema(
        schema,
        player_characters,
        character_snapshots,
    )
    stat_block = _find_bestiary_monster(schema, bestiary)
    class_record = find_class_record(schema, classes)
    equipment = Equipment(
        **{
            slot: _creature_item_id(item)
            for slot, item in cast(dict[str, object], dict(schema.equipment)).items()
        }
    )
    attributes = build_creature_attributes(schema, stat_block, class_record)
    class_features = resolve_class_features(class_record, schema.attributes.level)
    character_profile = build_character_profile(schema.character_profile)
    triggered_effects = [
        *resolve_optional_feature_effects(schema, optional_features),
        *feat_triggered_effects(character_profile),
    ]
    combat_profile = build_combat_profile(class_features)
    if character_profile is not None and any(
        feat.name.casefold() == "lucky" for feat in character_profile.feats
    ):
        combat_profile.feature_uses_max[LUCKY_FEATURE_ID] = attributes.proficiency_bonus
        combat_profile.feature_recharge[LUCKY_FEATURE_ID] = {"long_rest": "all"}
    spellcasting = build_spellcasting(
        schema,
        attributes,
        class_record,
        spells,
    )

    stat_block_actions = build_stat_block_actions(stat_block, spells)
    multiattack_action = (
        next(
            (
                action
                for action in stat_block.action
                if action.capability is not None
                and action.capability.type == "multiattack"
            ),
            None,
        )
        if stat_block is not None
        else None
    )
    return Creature(
        id=schema.id,
        name=schema.name or _stat_block_name(stat_block),
        description=schema.description,
        token_image=schema.token_image,
        current_health=schema.current_health,
        inventory=Inventory(
            items=[_creature_item_id(item) for item in schema.inventory]
        ),
        attributes=attributes,
        equipment=equipment,
        size=build_creature_size(schema, stat_block),
        class_ref=(
            ClassRef(name=schema.class_ref.name, source=schema.class_ref.source)
            if schema.class_ref
            else None
        ),
        character_profile=character_profile,
        class_features=class_features,
        triggered_effects=triggered_effects,
        combat_profile=combat_profile,
        feature_uses_remaining=build_feature_uses_remaining(combat_profile),
        multiattack=build_multiattack(
            cast(MultiattackCapabilitySchema, multiattack_action.capability)
            if multiattack_action is not None
            else None
        ),
        stat_block_actions=stat_block_actions,
        declared_stat_block_actions=build_declared_stat_block_actions(stat_block),
        spellcasting=spellcasting,
        statistics=build_creature_statistics(stat_block),
        max_health_override=(
            stat_block.average_hit_points if stat_block is not None else None
        ),
    )


def _resolve_creature_schema(
    instance: CreatureSchema,
    player_characters: PlayerCharacterTemplates | None,
    character_snapshots: CharacterSnapshotCatalog | None,
) -> CreatureSchema:
    if (
        instance.player_character is not None
        and instance.character_snapshot is not None
    ):
        raise ValueError(
            f"Creature '{instance.id}' cannot reference both a local player "
            "character and a canonical character snapshot."
        )
    if instance.player_character is None and instance.character_snapshot is None:
        return instance
    template: CreatureSchema
    if instance.character_snapshot is not None:
        if character_snapshots is None:
            raise ValueError(
                f"Creature '{instance.id}' references canonical build "
                f"'{instance.character_snapshot.build}', but no character "
                "snapshot catalog was loaded."
            )
        template = character_snapshots.creature_template(
            instance.character_snapshot.build,
            instance.character_snapshot.level,
        )
    else:
        if player_characters is None:
            raise ValueError(
                f"Creature '{instance.id}' references player character "
                f"'{instance.player_character}', but no player character catalog "
                "was loaded."
            )
        local_template = player_characters.get(instance.player_character or "")
        if local_template is None:
            raise KeyError(f"Player character '{instance.player_character}' not found.")
        template = local_template

    template_data = template.model_dump(
        exclude={"id", "player_character", "character_snapshot"}
    )
    instance_data = instance.model_dump(
        exclude_unset=True,
        exclude={
            "attributes",
            "player_character",
            "character_snapshot",
            "equipment",
            "inventory",
            "metadata",
            "optional_features",
            "spells_known",
        },
    )
    if "attributes" in instance.model_fields_set:
        instance_data["attributes"] = instance.attributes.model_dump()
    merged = {
        **template_data,
        **instance_data,
        "inventory": [
            *template.inventory,
            *instance.inventory,
        ],
        "equipment": {
            **template.equipment,
            **instance.equipment,
        },
        "metadata": {
            **template.metadata,
            **instance.metadata,
        },
        "optional_features": [
            *template.optional_features,
            *instance.optional_features,
        ],
        "spells_known": [
            *template.spells_known,
            *instance.spells_known,
        ],
    }
    return CreatureSchema.model_validate(merged)


def _creature_item_id(item: str | CreatureItemReferenceSchema | object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, CreatureItemReferenceSchema):
        return slug(item.name)
    if isinstance(item, dict):
        name = item.get("name")
        if isinstance(name, str):
            return slug(name)
    raise TypeError(f"Unsupported creature item reference: {item!r}")


def _find_bestiary_monster(
    schema: CreatureSchema,
    bestiary: BestiaryCatalog | None,
) -> BestiaryMonsterSchema | None:
    if schema.stat_block is None:
        return None
    if bestiary is None:
        raise ValueError(
            f"Creature references stat block '{schema.stat_block.name}', "
            "but no bestiary catalog was loaded."
        )
    return bestiary.find(schema.stat_block.name, schema.stat_block.source)


def _stat_block_name(stat_block: BestiaryMonsterSchema | None) -> str:
    if stat_block is None:
        raise ValueError("Creature must define either 'name' or 'stat_block'.")
    return stat_block.public_name
