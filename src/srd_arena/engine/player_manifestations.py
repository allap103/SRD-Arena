"""Recognize explicit symptoms, never infer diagnoses from hidden roll modifiers."""

from dataclasses import dataclass

from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent


@dataclass(frozen=True)
class ManifestedState:
    """Identify the exact state instance demonstrated by a recognizable symptom."""

    instance_id: str
    name: str
    is_condition: bool


def manifested_state(event: CombatEvent) -> ManifestedState | None:
    """Recognize supported manifestations emitted by focused rules handlers.

    Retching from Stinking Cloud identifies its Poisoned application and
    ongoing debuff. Generic application, failed saves, and attack misses do
    not diagnose a condition. Add further cases only with explicit evidence.
    """

    if event.data.get("manifestation") != "stinking_cloud_retching":
        return None
    if event.type == "condition_manifested":
        instance_id = event.data.get("condition_id")
        if event.data.get("condition") == "poisoned" and isinstance(instance_id, str):
            return ManifestedState(instance_id, "poisoned", True)
    if event.type == "effect_manifested":
        instance_id = event.data.get("effect_id")
        if event.data.get("definition_id") == "stinking_cloud" and isinstance(
            instance_id, str
        ):
            return ManifestedState(instance_id, "Stinking Cloud", False)
    return None
