"""Encode disclosed budgets and status with explicit collection-known flags."""

from srd_arena.engine.api import FilteredCreature

from .mechanics_encoding import CONDITIONS
from .spell_encoding import SPELL_IDS

RESOURCE_IDS = ("lucky", "rage")
RESOURCE_BUCKETS = (*RESOURCE_IDS, "other_feature", "other_resource")
DECISION_STATE_FEATURES = (
    "movement_budget_known",
    "movement_remaining_feet",
    "movement_total_feet",
    "action_economy_known",
    "actions_remaining",
    "bonus_action_available",
    "reaction_available",
    "attacks_remaining",
    "attacks_per_attack_action",
    "spell_slot_spent_this_turn",
    "resources_known",
    *(
        f"slot_{level}_{field}"
        for level in range(1, 10)
        for field in ("remaining", "maximum")
    ),
    *(
        f"resource_{name}_{field}"
        for name in RESOURCE_BUCKETS
        for field in ("remaining", "maximum")
    ),
    "conditions_known",
    "conditions_complete",
    *(f"condition_{name}" for name in CONDITIONS),
    "concentration_known",
    "concentrating",
    *(f"concentrating_on_{name}" for name in (*SPELL_IDS, "unknown")),
)


def decision_state_features(row: FilteredCreature) -> list[float]:
    """Distinguish hidden collections from known empty or exhausted collections."""
    movement, economy, resources = row.movement, row.action_economy, row.resources
    values = [
        float(movement is not None),
        movement.remaining_feet / 120 if movement else 0.0,
        movement.total_feet / 120 if movement else 0.0,
        float(economy is not None),
        economy.actions_remaining / 10 if economy else 0.0,
        float(economy.bonus_action_available) if economy else 0.0,
        float(economy.reaction_available) if economy else 0.0,
        economy.attacks_remaining / 10 if economy else 0.0,
        economy.attacks_per_attack_action / 10 if economy else 0.0,
        float(economy.spell_slot_spent_this_turn) if economy else 0.0,
        float(resources is not None),
    ]
    slots = {slot.level: slot for slot in resources.spell_slots} if resources else {}
    for level in range(1, 10):
        slot = slots.get(level)
        values.extend((slot.remaining / 10, slot.maximum / 10) if slot else (0.0, 0.0))
    buckets = {name: [0.0, 0.0] for name in RESOURCE_BUCKETS}
    for resource in resources.class_resources if resources else ():
        name = (
            resource.source_id
            if resource.kind == "feature_uses" and resource.source_id in RESOURCE_IDS
            else (
                "other_feature" if resource.kind == "feature_uses" else "other_resource"
            )
        )
        buckets[name][0] += resource.remaining / 10
        buckets[name][1] += resource.maximum / 10
    values.extend(value for bucket in buckets.values() for value in bucket)
    conditions = {
        name if name in CONDITIONS else "unknown" for name in row.conditions or ()
    }
    concentration = {
        name if name in SPELL_IDS else "unknown" for name in row.concentrating_on or ()
    }
    values.extend(
        (
            float(row.conditions is not None),
            float(row.conditions_complete is True),
            *(float(name in conditions) for name in CONDITIONS),
        )
    )
    values.extend(
        (
            float(row.concentrating_on is not None),
            float(bool(concentration)),
            *(float(name in concentration) for name in (*SPELL_IDS, "unknown")),
        )
    )
    return values
