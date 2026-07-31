from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .runtime import (
    EffectDuration,
    EffectSource,
    EffectSourceKind,
    Indefinite,
    RuntimeStateIdentity,
    UntilTurnEnd,
)
from .triggered import TriggeredEffect


class Condition(StrEnum):
    BLINDED = "blinded"
    CHARMED = "charmed"
    DEAFENED = "deafened"
    EXHAUSTION = "exhaustion"
    FRIGHTENED = "frightened"
    GRAPPLED = "grappled"
    INCAPACITATED = "incapacitated"
    INVISIBLE = "invisible"
    PARALYZED = "paralyzed"
    PETRIFIED = "petrified"
    POISONED = "poisoned"
    PRONE = "prone"
    RESTRAINED = "restrained"
    STUNNED = "stunned"
    UNCONSCIOUS = "unconscious"


class CombatTrait(StrEnum):
    CANNOT_TAKE_ACTIONS = "cannot_take_actions"
    CANNOT_TAKE_REACTIONS = "cannot_take_reactions"
    SPEED_ZERO = "speed_zero"


@dataclass(frozen=True)
class AppliedCondition:
    identity: RuntimeStateIdentity
    condition: Condition
    target_ref: str
    duration: EffectDuration = field(default_factory=Indefinite)
    value: int | None = None
    triggered_effects: tuple[TriggeredEffect, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.condition is Condition.EXHAUSTION:
            if self.value is None or not 1 <= self.value <= 6:
                raise ValueError("Exhaustion requires a level from 1 through 6.")
        elif self.value is not None:
            raise ValueError(
                f"{self.condition.value} does not accept a condition value."
            )

    @property
    def id(self) -> str:
        return self.identity.id

    @property
    def source_ref(self) -> str | None:
        return self.identity.source.creature_ref

    @property
    def source_label(self) -> str:
        return (
            self.identity.source.label
            or self.identity.source.creature_ref
            or self.identity.source.definition_id
        )


def build_applied_condition(
    *,
    condition: Condition,
    source_ref: str,
    source_label: str,
    target_ref: str,
    duration: EffectDuration | None = None,
    expires_on_creature_ref: str | None = None,
    expires_on_round: int | None = None,
    metadata: dict[str, object] | None = None,
    value: int | None = None,
) -> AppliedCondition:
    condition_id = f"condition:{condition.value}:{source_ref}:{target_ref}"
    if duration is None:
        duration = (
            UntilTurnEnd(expires_on_creature_ref, expires_on_round)
            if expires_on_creature_ref is not None
            else Indefinite()
        )
    source = EffectSource(
        kind=EffectSourceKind.CREATURE,
        definition_id=source_ref,
        creature_ref=source_ref,
        label=source_label,
    )
    return AppliedCondition(
        identity=RuntimeStateIdentity(id=condition_id, source=source),
        condition=condition,
        target_ref=target_ref,
        duration=duration,
        value=value,
        triggered_effects=_condition_effects(condition, target_ref),
        metadata=dict(metadata or {}),
    )


def _condition_effects(
    condition: Condition,
    target_ref: str,
) -> tuple[TriggeredEffect, ...]:
    if condition is not Condition.BLINDED:
        return ()
    return (
        TriggeredEffect(
            id=f"{condition.value}:attack-disadvantage:{target_ref}",
            source_type="condition",
            source_id=condition.value,
            trigger="attack_roll_created",
            operation="grant_disadvantage",
            conditions={"attacker_ref": target_ref},
        ),
        TriggeredEffect(
            id=f"{condition.value}:defender-advantage:{target_ref}",
            source_type="condition",
            source_id=condition.value,
            trigger="attack_roll_created",
            operation="grant_advantage",
            conditions={"target_ref": target_ref},
        ),
    )
