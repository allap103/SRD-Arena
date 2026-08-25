"""Coordinate resolution for every primary spell target."""

from dataclasses import dataclass

from ...capabilities import (
    AttackResolution,
    AutomaticResolution,
    SavingThrowResolution,
)
from .context import SpellActionContext, SpellTargetContext
from .preparation import PreparedSpellResolution
from .target_damage import apply_target_damage
from .target_restoration import restore_target
from .target_rolls import resolve_target_roll


@dataclass
class ResolvedSpellTargets:
    messages: list[tuple[str, str]]
    save_details: list[dict[str, object]]
    attack_details: list[dict[str, object]]
    damage_details: list[dict[str, object]]
    healing_details: list[dict[str, object]]
    temporary_hit_point_details: list[dict[str, object]]
    affected_targets: list[SpellTargetContext]


def resolve_spell_targets(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
) -> ResolvedSpellTargets:
    """Resolve rolls, damage, restoration, and messages in target order."""

    target_suffix = (
        f" on {prepared.targets[0].target_label}"
        if prepared.definition.target.kind == "creature"
        and len(prepared.targets) == 1
        else ""
    )
    messages = [
        (
            "system",
            f"{context.creature.name} casts {context.spell.name}{target_suffix}.",
        )
    ]
    save_details: list[dict[str, object]] = []
    attack_details: list[dict[str, object]] = []
    damage_details: list[dict[str, object]] = []
    healing_details: list[dict[str, object]] = []
    temporary_hit_point_details: list[dict[str, object]] = []
    affected_targets: list[SpellTargetContext] = []

    for target in prepared.targets:
        roll_outcome = resolve_target_roll(
            context,
            prepared,
            target,
            projectile_index=len(attack_details) + 1,
        )
        if roll_outcome.save_detail is not None:
            save_details.append(roll_outcome.save_detail)
        if roll_outcome.attack_detail is not None:
            attack_details.append(roll_outcome.attack_detail)

        damage = apply_target_damage(target, prepared, roll_outcome)
        damage_details.extend(damage.details)
        affected = (
            isinstance(prepared.resolution, SavingThrowResolution)
            and not roll_outcome.successful_save
        ) or (
            isinstance(
                prepared.resolution,
                (AttackResolution, AutomaticResolution),
            )
            and roll_outcome.hit
        )
        if affected:
            affected_targets.append(target)
            restoration = restore_target(context, prepared, target)
            healing_details.extend(restoration.healing_details)
            temporary_hit_point_details.extend(
                restoration.temporary_hit_point_details
            )

        outcome_label = (
            "damages"
            if damage.total_applied > 0
            else "heals"
            if any(
                detail["target_ref"] == target.target_ref for detail in healing_details
            )
            else "wards"
            if any(
                detail["target_ref"] == target.target_ref
                for detail in temporary_hit_point_details
            )
            else "affects"
            if affected
            else "does not affect"
        )
        if not context.spell.removable_conditions:
            if roll_outcome.automatic_success_reasons:
                messages.append(
                    (
                        "system",
                        f"{target.target_label} is unaffected by "
                        f"{context.spell.name}: "
                        f"{'; '.join(roll_outcome.automatic_success_reasons)}.",
                    )
                )
            elif (
                isinstance(prepared.resolution, SavingThrowResolution)
                and roll_outcome.successful_save
                and damage.total_applied == 0
            ):
                messages.append(
                    (
                        "system",
                        f"{target.target_label} resists {context.spell.name} "
                        f"with a successful "
                        f"{(prepared.save_ability or 'dexterity').title()} save.",
                    )
                )
            else:
                messages.append(
                    (
                        "system",
                        f"{context.spell.name} {outcome_label} {target.target_label}.",
                    )
                )

    return ResolvedSpellTargets(
        messages=messages,
        save_details=save_details,
        attack_details=attack_details,
        damage_details=damage_details,
        healing_details=healing_details,
        temporary_hit_point_details=temporary_hit_point_details,
        affected_targets=affected_targets,
    )
