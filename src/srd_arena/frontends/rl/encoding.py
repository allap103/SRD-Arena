"""Versioned, intentionally small encoder for the single-encounter experiment."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from srd_arena.engine.api import FilteredCreature, FilteredObservation
from srd_arena.frontends.rl.actions import Candidate
from srd_arena.frontends.rl.spell_encoding import (
    SPELL_FEATURES,
    SPELL_NUMBERS,
    spell_features,
)

ENCODER_SCHEMA_ID = "experimental-encoder-v6"
type Array = NDArray[np.float64]
# A checked, versioned registry. Unlisted kinds share the final unknown bucket.
ACTION_KINDS = (
    "attack",
    "spell",
    "feature",
    "utilize",
    "move",
    "movement",
    "dash",
    "disengage",
    "dodge",
    "help",
    "hide",
    "wait",
    "grapple",
    "escape_grapple",
    "keep_initiative",
    "swap_initiative",
    "decline_d20_modifier",
    "use_d20_modifier",
    "decline_reaction",
    "reaction",
    "toggle_spell_target",
    "set_spell_resource_allocation",
    "confirm_spell_targets",
    "cancel_spell_targets",
    "use_weapon_mastery",
    "decline_weapon_mastery",
    "use_reckless_attack",
    "decline_reckless_attack",
    "stand_up",
    "drop_prone",
)
ENTITY_FEATURES = (
    "own",
    "ally",
    "enemy",
    "current",
    "last_known",
    "unknown",
    "visible",
    "x",
    "y",
    "position_known",
    "health_fraction",
    "exact_health_known",
    "health_lower",
    "health_upper",
    "interval_known",
    "lower_inclusive",
    "upper_inclusive",
    "temporary_hp",
    "temporary_exact_known",
    "temporary_present",
    "temporary_presence_known",
    "armor_class",
    "armor_class_known",
    "defeated",
    "defeated_known",
    "observed_damage",
    "observed_damage_known",
    "is_decision_actor",
    "selected_target_count",
)
GLOBAL_FEATURES = (
    "width",
    "height",
    "round",
    "round_known",
    "sunlight",
    "sunlight_known",
    "targeting",
    "selected_count",
    "maximum_targets",
    "pool_total",
    "pool_known",
)
ACTION_FEATURES = (
    *ACTION_KINDS,
    "unknown_kind",
    "aim_x",
    "aim_y",
    "aim_known",
    "amount",
    "amount_known",
    "remove",
    "cast_complete",
    "coverage_known",
    "affected_own_count",
    "affected_ally_count",
    "affected_enemy_count",
    "movement_destination_x",
    "movement_destination_y",
    "movement_destination_known",
    "movement_dx",
    "movement_dy",
    "movement_displacement_known",
    "movement_cost",
    "movement_cost_known",
    *SPELL_FEATURES,
)


def _known(value: float | int | bool | None, scale: float = 1) -> tuple[float, float]:
    return (0.0, 0.0) if value is None else (float(value) / scale, 1.0)


def _entity(row: FilteredCreature, observation: FilteredObservation) -> list[float]:
    exact = (
        row.health is not None
        and row.health.current is not None
        and row.health.maximum is not None
    )
    interval = row.health.interval if row.health else None
    fraction = 0.0
    if exact:
        assert (
            row.health is not None
            and row.health.current is not None
            and row.health.maximum is not None
        )
        if row.health.maximum <= 0:
            raise ValueError("Cannot encode nonpositive maximum HP")
        fraction = row.health.current / row.health.maximum
    temporary = row.temporary_health
    target_count = (
        observation.targeting.selected_target_refs.count(row.creature_ref)
        if observation.targeting
        else 0
    )
    return [
        float(row.allegiance == "own"),
        float(row.allegiance == "ally"),
        float(row.allegiance == "enemy"),
        float(row.knowledge == "current"),
        float(row.knowledge == "last_known"),
        float(row.knowledge == "unknown"),
        float(row.currently_visible),
        row.position.x / 24 if row.position else 0.0,
        row.position.y / 24 if row.position else 0.0,
        float(row.position is not None),
        fraction,
        float(exact),
        interval.lower if interval else 0.0,
        interval.upper if interval else 0.0,
        float(interval is not None),
        float(interval.lower_inclusive) if interval else 0.0,
        float(interval.upper_inclusive) if interval else 0.0,
        float(temporary) / 100 if type(temporary) is int else 0.0,
        float(type(temporary) is int),
        float(temporary) if type(temporary) is bool else 0.0,
        float(type(temporary) is bool),
        *_known(row.armor_class, 30),
        *_known(row.defeated),
        *_known(row.observed_damage_total, 100),
        float(row.creature_ref == observation.decision.creature_ref),
        target_count / 10,
    ]


@dataclass(frozen=True)
class EncodedObservation:
    """Fixed entity capacity and variable decision-local candidate rows.

    Entity IDs and command tokens never enter numerical arrays. Actor/target
    indices refer only to stable slots assigned at reset. Padded slots are
    distinguished by entity_mask; candidate rows are all admitted attempts.
    """

    global_features: Array
    entities: Array
    entity_mask: NDArray[np.bool_]
    actions: Array
    actor_slots: NDArray[np.int64]
    target_slots: NDArray[np.int64]
    action_mask: NDArray[np.bool_]
    affected_entity_mask: NDArray[np.bool_]
    selected_entity_weights: Array


class Encoder:
    """Freeze stable entity slots at reset and encode only filtered DTOs."""

    def __init__(self, initial: FilteredObservation, *, max_entities: int = 10) -> None:
        if len(initial.creatures) > max_entities:
            raise ValueError("Encounter exceeds entity capacity")
        self.refs = tuple(
            c.creature_ref
            for c in sorted(
                initial.creatures,
                key=lambda c: (
                    c.allegiance != "own",
                    c.allegiance == "enemy",
                    c.creature_ref,
                ),
            )
        )
        self.max_entities = max_entities

    def encode(
        self, observation: FilteredObservation, choices: tuple[Candidate, ...]
    ) -> EncodedObservation:
        """Return finite numeric features with explicit missing-value indicators."""
        if (
            not 1 <= observation.grid.width <= 24
            or not 1 <= observation.grid.height <= 24
        ):
            raise ValueError("Experimental encoder supports boards up to 24 by 24")
        if set(c.creature_ref for c in observation.creatures) != set(self.refs):
            raise ValueError("Roster changed without resetting the encoder")
        targeting = observation.targeting
        global_features = np.array(
            [
                observation.grid.width / 24,
                observation.grid.height / 24,
                *_known(observation.round_number, 100),
                *_known(observation.sunlight),
                float(targeting is not None),
                len(targeting.selected_target_refs) / 10 if targeting else 0.0,
                targeting.maximum_targets / 10 if targeting else 0.0,
                *_known(targeting.resource_pool_total if targeting else None, 100),
            ],
            dtype=np.float64,
        )
        entities = np.zeros((self.max_entities, len(ENTITY_FEATURES)))
        by_ref = {c.creature_ref: c for c in observation.creatures}
        for slot, ref in enumerate(self.refs):
            entities[slot] = _entity(by_ref[ref], observation)
        action_rows = np.zeros((len(choices), len(ACTION_FEATURES)))
        actors = np.full(len(choices), -1, dtype=np.int64)
        targets = np.full(len(choices), -1, dtype=np.int64)
        affected = np.zeros((len(choices), self.max_entities), dtype=np.bool_)
        selected = np.zeros((len(choices), 3, self.max_entities))
        slots = {ref: slot for slot, ref in enumerate(self.refs)}
        spell_vectors: dict[int, tuple[float, ...]] = {}
        for index, choice in enumerate(choices):
            movement = choice.movement
            destination = movement.destination if movement else None
            descriptor_key = id(choice.spell)
            if descriptor_key not in spell_vectors:
                spell_vectors[descriptor_key] = spell_features(choice.spell)
            kind = (
                ACTION_KINDS.index(choice.kind)
                if choice.kind in ACTION_KINDS
                else len(ACTION_KINDS)
            )
            action_rows[index, kind] = 1.0
            action_rows[index, len(ACTION_KINDS) + 1 :] = (
                choice.aim[0] / 24 if choice.aim else 0.0,
                choice.aim[1] / 24 if choice.aim else 0.0,
                float(choice.aim is not None),
                *_known(choice.amount, 100),
                float(choice.remove),
                float(choice.cast_complete),
                float(choice.affected_refs is not None),
                *(
                    sum(
                        by_ref[ref].allegiance == group
                        for ref in (choice.affected_refs or ())
                    )
                    / 10
                    for group in ("own", "ally", "enemy")
                ),
                destination.x / 24 if destination else 0.0,
                destination.y / 24 if destination else 0.0,
                float(destination is not None),
                movement.displacement[0] if movement else 0.0,
                movement.displacement[1] if movement else 0.0,
                float(movement is not None),
                *_known(movement.cost if movement else None, 24),
                *spell_vectors[descriptor_key],
            )
            for order, ref in enumerate(choice.selected_refs):
                selected[index, 0, slots[ref]] += 1
                selected[index, 1, slots[ref]] += 1 / (order + 1)
            for ref, amount in choice.allocations:
                selected[index, 2, slots[ref]] = amount / 100
            for ref in choice.affected_refs or ():
                affected[index, slots[ref]] = True
            actors[index] = slots.get(choice.actor_ref, -1)
            targets[index] = (
                slots.get(choice.target_ref, -1) if choice.target_ref else -1
            )
        encoded = EncodedObservation(
            global_features,
            entities,
            np.arange(self.max_entities) < len(self.refs),
            action_rows,
            actors,
            targets,
            np.ones(len(choices), dtype=np.bool_),
            affected,
            selected,
        )
        for array in (global_features, entities, action_rows):
            if not np.isfinite(array).all():
                raise ValueError("Encoder produced nonfinite features")
        return encoded


def encoder_manifest() -> dict[str, object]:
    """Describe feature order and fixed normalization for saved experiments."""
    return {
        "schema_id": ENCODER_SCHEMA_ID,
        "entity_features": ENTITY_FEATURES,
        "global_features": GLOBAL_FEATURES,
        "action_features": ACTION_FEATURES,
        "scales": {
            "coordinates": 24,
            "health_and_resources": 100,
            "armor_class": 30,
            "round": 100,
            "target_counts": 10,
            "movement_cost_grid_units": 24,
            "movement_displacement_cells": 1,
        },
        "movement": {
            "schema": "advertised-grid-step-v1",
            "destination": "current_disclosed_actor_position_plus_displacement",
            "cost": "advertised_grid_movement_units_not_euclidean_distance",
            "missing_information": "explicit_known_flags",
            "availability": "player_safe_attempt_no_private_legality_probe",
        },
        "spell_selection": {
            "schema": "complete-cast-v1",
            "assembly": "monotonic_local_choices_one_engine_submission",
            "entity_channels": [
                "target_count",
                "reciprocal_order_weight",
                "allocated_resource_divided_by_100",
            ],
        },
        "coverage": {
            "schema": "area-disclosed-footprints-v2",
            "affected_entity_mask": "candidate_by_stable_entity_slot",
            "aim_grammar": "existing_integer_coordinates",
            "membership": "current_disclosed_living_footprints_after_total_cover",
            "aim_retention": "all_integer_coordinates_no_grouping",
            "missing_information": "all_aims_with_unknown_coverage",
        },
        "spell_scales": SPELL_NUMBERS,
        "mechanics_scales": {
            "quantities": 100,
            "duration_rounds": 100,
            "distance_feet": 120,
            "caster_level": 20,
            "casting_modifier": 20,
        },
        "omitted": [
            "coverage_for_unsupported_area_geometry",
            "coverage_after_movement",
            "full_requirement_and_custom_rule_interpretation",
            "contextual_spell_feature_modifiers",
            "terrain",
            "appearance",
            "size",
            "type",
            "event_sequence",
            "initiative_order",
            "optional_decision_context",
        ],
    }
