"""Extract non-privileged facts from structured combat events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent

from .observability import Observability, condition_observability
from .player_observation_models import (
    PublicCombatEventObservation,
    PublicEventKind,
)


@dataclass(frozen=True)
class PublicDamage:
    """Describe damage to one creature as reported by a combat event."""

    target_ref: str
    amount: int


def public_damage_from_event(event: CombatEvent) -> tuple[PublicDamage, ...]:
    """Return applied creature damage encoded by one supported event shape."""

    data = event.data
    if event.type == "attack_resolved":
        return _single_damage(data, target_key="target_ref", amount_key="damage")
    if event.type == "attack_hit_retaliation":
        return _single_damage(data, target_key="attacker_ref", amount_key="damage")
    if event.type == "stat_block_action_resolved":
        outcomes = _mapping_sequence(data.get("outcomes"))
        if outcomes:
            return tuple(
                damage
                for outcome in outcomes
                for damage in _single_damage(
                    outcome,
                    target_key="target_ref",
                    amount_key="damage",
                )
            )
        return _single_damage(data, target_key="target_ref", amount_key="damage")
    if event.type in {
        "spell_cast",
        "spell_projectile_resolved",
        "ongoing_effect_resolved",
    }:
        return tuple(
            damage
            for detail in _mapping_sequence(data.get("damage_roll_details"))
            for damage in _single_damage(
                detail,
                target_key="target_ref",
                amount_key="applied_damage",
            )
        )
    return ()


def public_events_from_event(
    event: CombatEvent,
    *,
    visible_creature_refs: frozenset[str],
) -> tuple[PublicCombatEventObservation, ...]:
    """Project one internal event into conservative player-visible records."""

    if event.type == "attack_resolved":
        return _attack_event(event, visible_creature_refs)
    if event.type == "attack_hit_retaliation":
        return _retaliation_event(event, visible_creature_refs)
    if event.type == "stat_block_action_resolved":
        return _stat_block_events(event, visible_creature_refs)
    if event.type in {"spell_cast", "spell_projectile_resolved"}:
        return _spell_events(event, visible_creature_refs)
    if event.type == "movement_resolved":
        actor_ref = _visible_ref(event.creature_ref, visible_creature_refs)
        if actor_ref is None:
            return ()
        return (
            PublicCombatEventObservation(
                event.seq,
                PublicEventKind.MOVEMENT,
                actor_ref=actor_ref,
                outcome="moved",
            ),
        )
    if event.type == "creature_defeated":
        return _defeat_event(event, visible_creature_refs)
    if event.type in {"condition_applied", "condition_removed"}:
        return _condition_event(event, visible_creature_refs)
    if event.type == "feature_used":
        return _source_use_event(
            event,
            visible_creature_refs,
            kind=PublicEventKind.FEATURE,
            source_key="feature_id",
            source_prefix="feature",
        )
    if event.type == "item_used":
        return _source_use_event(
            event,
            visible_creature_refs,
            kind=PublicEventKind.ITEM,
            source_key="item_id",
            source_prefix="item",
        )
    return ()


def _attack_event(
    event: CombatEvent,
    visible_refs: frozenset[str],
) -> tuple[PublicCombatEventObservation, ...]:
    actor_ref = _visible_ref(event.creature_ref, visible_refs)
    target_ref = _visible_ref(_string(event.data.get("target_ref")), visible_refs)
    if actor_ref is None and target_ref is None:
        return ()
    hit = _boolean(event.data.get("hit"))
    critical = _boolean(event.data.get("critical_hit"))
    outcome = (
        "critical_hit"
        if hit and critical
        else "hit"
        if hit
        else "miss"
        if hit is False
        else None
    )
    return (
        PublicCombatEventObservation(
            event.seq,
            PublicEventKind.ATTACK,
            actor_ref=actor_ref,
            target_ref=target_ref,
            source_id=_source_id(
                "attack",
                event.data.get("attack_name"),
                visible=actor_ref is not None,
            ),
            outcome=outcome,
            amount=_positive_int(event.data.get("damage"))
            if target_ref is not None
            else None,
        ),
    )


def _retaliation_event(
    event: CombatEvent,
    visible_refs: frozenset[str],
) -> tuple[PublicCombatEventObservation, ...]:
    actor_ref = _visible_ref(event.creature_ref, visible_refs)
    target_ref = _visible_ref(_string(event.data.get("attacker_ref")), visible_refs)
    if actor_ref is None and target_ref is None:
        return ()
    return (
        PublicCombatEventObservation(
            event.seq,
            PublicEventKind.RETALIATION,
            actor_ref=actor_ref,
            target_ref=target_ref,
            source_id=_source_id(
                "feature",
                event.data.get("source_definition_id"),
                visible=actor_ref is not None,
            ),
            outcome="damage",
            amount=_positive_int(event.data.get("damage"))
            if target_ref is not None
            else None,
        ),
    )


def _stat_block_events(
    event: CombatEvent,
    visible_refs: frozenset[str],
) -> tuple[PublicCombatEventObservation, ...]:
    actor_ref = _visible_ref(event.creature_ref, visible_refs)
    source_id = _source_id(
        "stat_block",
        event.data.get("action_name"),
        visible=actor_ref is not None,
    )
    outcomes = _mapping_sequence(event.data.get("outcomes"))
    projected = tuple(
        PublicCombatEventObservation(
            event.seq,
            PublicEventKind.STAT_BLOCK_ACTION,
            actor_ref=actor_ref,
            target_ref=target_ref,
            source_id=source_id,
            outcome=_save_outcome(outcome.get("success")),
            amount=_positive_int(outcome.get("damage")),
        )
        for outcome in outcomes
        if (
            target_ref := _visible_ref(
                _string(outcome.get("target_ref")),
                visible_refs,
            )
        )
        is not None
    )
    if projected or actor_ref is None:
        return projected
    return (
        PublicCombatEventObservation(
            event.seq,
            PublicEventKind.STAT_BLOCK_ACTION,
            actor_ref=actor_ref,
            source_id=source_id,
        ),
    )


def _spell_events(
    event: CombatEvent,
    visible_refs: frozenset[str],
) -> tuple[PublicCombatEventObservation, ...]:
    actor_ref = _visible_ref(event.creature_ref, visible_refs)
    source_id = _source_id(
        "spell",
        event.data.get("spell_id"),
        visible=actor_ref is not None,
    )
    candidate_refs = dict.fromkeys(
        (
            *_string_sequence(event.data.get("target_refs")),
            *(
                (target_ref,)
                if (target_ref := _string(event.data.get("target_ref"))) is not None
                else ()
            ),
            *(damage.target_ref for damage in public_damage_from_event(event)),
        )
    )
    damage_by_target: dict[str, int] = {}
    for damage in public_damage_from_event(event):
        damage_by_target[damage.target_ref] = (
            damage_by_target.get(damage.target_ref, 0) + damage.amount
        )
    visible_targets = tuple(
        target_ref for target_ref in candidate_refs if target_ref in visible_refs
    )
    if visible_targets:
        return tuple(
            PublicCombatEventObservation(
                event.seq,
                PublicEventKind.SPELL,
                actor_ref=actor_ref,
                target_ref=target_ref,
                source_id=source_id,
                outcome="resolved",
                amount=damage_by_target.get(target_ref),
            )
            for target_ref in visible_targets
        )
    if actor_ref is None:
        return ()
    return (
        PublicCombatEventObservation(
            event.seq,
            PublicEventKind.SPELL,
            actor_ref=actor_ref,
            source_id=source_id,
            outcome="resolved",
        ),
    )


def _defeat_event(
    event: CombatEvent,
    visible_refs: frozenset[str],
) -> tuple[PublicCombatEventObservation, ...]:
    target_ref = _visible_ref(event.creature_ref, visible_refs)
    if target_ref is None:
        return ()
    actor_ref = _visible_ref(
        _string(event.data.get("defeated_by_ref")),
        visible_refs,
    )
    return (
        PublicCombatEventObservation(
            event.seq,
            PublicEventKind.DEFEAT,
            actor_ref=actor_ref,
            target_ref=target_ref,
            outcome="defeated",
        ),
    )


def _condition_event(
    event: CombatEvent,
    visible_refs: frozenset[str],
) -> tuple[PublicCombatEventObservation, ...]:
    target_ref = _visible_ref(event.creature_ref, visible_refs)
    condition_value = _string(event.data.get("condition"))
    if target_ref is None or condition_value is None:
        return ()
    try:
        condition = Condition(condition_value)
    except ValueError:
        return ()
    if condition_observability(condition) is not Observability.OBVIOUS:
        return ()
    return (
        PublicCombatEventObservation(
            event.seq,
            PublicEventKind.CONDITION,
            target_ref=target_ref,
            source_id=f"condition:{condition.value}",
            outcome="applied" if event.type == "condition_applied" else "removed",
        ),
    )


def _source_use_event(
    event: CombatEvent,
    visible_refs: frozenset[str],
    *,
    kind: PublicEventKind,
    source_key: str,
    source_prefix: str,
) -> tuple[PublicCombatEventObservation, ...]:
    actor_ref = _visible_ref(event.creature_ref, visible_refs)
    if actor_ref is None:
        return ()
    return (
        PublicCombatEventObservation(
            event.seq,
            kind,
            actor_ref=actor_ref,
            source_id=_source_id(
                source_prefix,
                event.data.get(source_key),
                visible=True,
            ),
            outcome="used",
        ),
    )


def _single_damage(
    data: Mapping[str, object],
    *,
    target_key: str,
    amount_key: str,
) -> tuple[PublicDamage, ...]:
    target_ref = data.get(target_key)
    amount = data.get(amount_key)
    if (
        not isinstance(target_ref, str)
        or not isinstance(amount, int)
        or isinstance(amount, bool)
        or amount <= 0
    ):
        return ()
    return (PublicDamage(target_ref, amount),)


def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _visible_ref(
    creature_ref: str | None,
    visible_refs: frozenset[str],
) -> str | None:
    return creature_ref if creature_ref in visible_refs else None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _positive_int(value: object) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None
    return value


def _source_id(prefix: str, value: object, *, visible: bool) -> str | None:
    if not visible or not isinstance(value, str) or not value:
        return None
    slug = "_".join(value.casefold().replace("-", " ").split())
    return f"{prefix}:{slug}"


def _save_outcome(value: object) -> str | None:
    success = _boolean(value)
    if success is None:
        return None
    return "save_succeeded" if success else "save_failed"
