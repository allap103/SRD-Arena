from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    CreatureSchema,
    build_creature,
    load_bestiary_catalog,
)
from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.creatures import (
    ApparentArmorCategory,
    ObservableAppearance,
)
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.engine.api import HealthBand, KnowledgeState, Session


def _session() -> Session:
    return Session(
        EncounterCatalog().load_encounter("warlock_training"),
        seed=42,
    )


def test_player_observation_exposes_appearance_but_not_enemy_statistics() -> None:
    session = _session()

    goblin = session.observe_player("heroes").creature("goblin_1")

    assert goblin.knowledge is KnowledgeState.VISIBLE
    assert goblin.appearance is not None
    assert goblin.appearance.armor_label == "Leather Armor"
    assert goblin.appearance.armor_category == "light"
    assert goblin.appearance.has_shield is True
    assert goblin.appearance.visible_weapons == ("Scimitar", "Shortbow")
    assert goblin.armor_class is None
    assert goblin.health is None
    assert goblin.maximum_health is None


def test_authored_appearance_overlays_inferred_equipment() -> None:
    session = _session()

    warlock = session.observe_player("heroes").creature("warlock")

    assert warlock.appearance is not None
    assert warlock.appearance.armor_label == "Studded Leather Armor"
    assert warlock.appearance.armor_category == "light"
    assert warlock.appearance.visible_weapons == ("Sickle", "Dagger")
    assert warlock.appearance.spellcasting_focus_label == "Orb"
    assert warlock.appearance.spellcasting_focus_kind == "arcane"
    assert warlock.appearance.apparent_creature_type == "Humanoid"


def test_mechanical_creature_type_is_not_inferred_as_visible() -> None:
    creature = build_creature(
        CreatureSchema.model_validate(
            {
                "id": "unidentified_aboleth",
                "stat_block": {"name": "Aboleth", "source": "XMM"},
            }
        ),
        bestiary=load_bestiary_catalog(SYSTEM_CONTENT_ROOT),
    )

    assert creature.statistics.creature_type == "aberration"
    assert creature.observable_appearance.apparent_creature_type is None


def test_hidden_armor_class_changes_do_not_change_enemy_observation() -> None:
    session = _session()
    before = session.observe_player("heroes").creature("goblin_1")
    assert session.encounter_state is not None

    session.encounter_state.creatures[
        "goblin_1"
    ].creature.attributes.base_armor_class = 99
    after = session.observe_player("heroes").creature("goblin_1")

    assert after == before


def test_visible_appearance_changes_are_observed() -> None:
    session = _session()
    session.observe_player("heroes")
    assert session.encounter_state is not None
    goblin = session.encounter_state.creatures["goblin_1"].creature
    goblin.observable_appearance = ObservableAppearance(
        armor_label="Plate Armor",
        armor_category=ApparentArmorCategory.HEAVY,
        visible_weapons=("Scimitar",),
    )

    observed = session.observe_player("heroes").creature("goblin_1")

    assert observed.appearance is not None
    assert observed.appearance.armor_category == "heavy"


def test_enemy_health_uses_bands_and_observed_damage() -> None:
    session = _session()
    session.observe_player("heroes")
    assert session.encounter_state is not None
    goblin = session.encounter_state.creatures["goblin_1"].creature

    goblin.take_damage(3)
    observed = session.observe_player("heroes").creature("goblin_1")

    assert observed.health is None
    assert observed.maximum_health is None
    assert observed.health_band is HealthBand.WOUNDED
    assert observed.observed_damage_total == 3


def test_only_obvious_enemy_conditions_are_exposed() -> None:
    session = _session()
    session.observe_player("heroes")
    assert session.encounter_state is not None
    state = session.encounter_state
    state.conditions.extend(
        (
            build_applied_condition(
                condition=Condition.PRONE,
                source_ref="warlock",
                source_label="Warlock",
                target_ref="goblin_1",
            ),
            build_applied_condition(
                condition=Condition.CHARMED,
                source_ref="warlock",
                source_label="Warlock",
                target_ref="goblin_1",
            ),
        )
    )

    observed = session.observe_player("heroes").creature("goblin_1")

    assert observed.known_conditions == ("prone",)


def test_hidden_enemy_retains_only_last_known_position() -> None:
    session = _session()
    visible = session.observe_player("heroes").creature("goblin_1")
    assert session.encounter_state is not None
    session.encounter_state.conditions.append(
        build_applied_condition(
            condition=Condition.INVISIBLE,
            source_ref="goblin_1",
            source_label="Goblin Warrior",
            target_ref="goblin_1",
        )
    )

    hidden = session.observe_player("heroes").creature("goblin_1")

    assert hidden.knowledge is KnowledgeState.LAST_KNOWN
    assert hidden.currently_visible is False
    assert hidden.position == visible.position
    assert hidden.health is None
    assert hidden.maximum_health is None
    assert hidden.armor_class is None
