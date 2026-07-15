from __future__ import annotations

from dataclasses import dataclass, field

from .rules.types import RuleGrant

RELATIONAL_STATUS_NAMES = {"grappled", "grappling"}


@dataclass(frozen=True)
class Status:
    id: str
    name: str
    source_ref: str
    source_label: str
    target_ref: str
    expires_on_actor_ref: str | None = None
    expires_on_round: int | None = None
    rules: list[RuleGrant] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class StatusSnapshot:
    id: str
    name: str
    source_ref: str
    source_label: str
    target_ref: str
    expires_on_actor_ref: str | None = None
    expires_on_round: int | None = None


def build_named_status(
    *,
    name: str,
    source_ref: str,
    source_label: str,
    target_ref: str,
    expires_on_actor_ref: str | None = None,
    expires_on_round: int | None = None,
) -> Status:
    return Status(
        id=_status_id(name=name, source_ref=source_ref, target_ref=target_ref),
        name=name,
        source_ref=source_ref,
        source_label=source_label,
        target_ref=target_ref,
        expires_on_actor_ref=expires_on_actor_ref,
        expires_on_round=expires_on_round,
        rules=_status_rules(name, target_ref),
        tags={name, "condition"},
    )


def _status_rules(name: str, target_ref: str) -> list[RuleGrant]:
    if name != "blinded":
        return []
    return [
        RuleGrant(
            id=f"{name}:attack-disadvantage:{target_ref}",
            source_type="condition",
            source_id=name,
            trigger="attack_roll_created",
            operation="grant_disadvantage",
            conditions={"attacker_ref": target_ref},
        ),
        RuleGrant(
            id=f"{name}:defender-advantage:{target_ref}",
            source_type="condition",
            source_id=name,
            trigger="attack_roll_created",
            operation="grant_advantage",
            conditions={"target_ref": target_ref},
        ),
    ]


def _status_id(*, name: str, source_ref: str, target_ref: str) -> str:
    if name in RELATIONAL_STATUS_NAMES:
        return f"{name}:{source_ref}:{target_ref}"
    return f"{name}:{target_ref}"
