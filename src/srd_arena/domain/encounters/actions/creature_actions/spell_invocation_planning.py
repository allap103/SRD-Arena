"""Plan pre-invocation spell targeting and automated controller choices."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import HealingEffect, capability_effects
from srd_arena.domain.spells.definitions import Spell
from srd_arena.domain.spells.rules import (
    SpellActionPayload,
    spell_chooses_area_targets,
    spell_max_targets,
    spell_repeats_target_allocations,
    spell_requires_full_target_count,
)

from ...rule_queries.health import effective_maximum_health
from ..option_discovery.spell_areas import spell_area_targets
from ..option_discovery.spell_targets import spell_action_targets

if TYPE_CHECKING:
    from srd_arena.domain.creatures import Creature

    from ...encounter import EncounterState


@dataclass(frozen=True)
class SpellInvocationPlan:
    """Describe targeting choices required before one spell invocation starts."""

    spell_id: str
    spell: Spell | None
    aim_point: tuple[float, float] | None
    slot_level: int | None
    selected_target_refs: tuple[str, ...]
    maximum_targets: int
    repeat_target_allocations: bool
    require_full_target_count: bool
    resource_pool_total: int | None
    resource_allocation_limits: dict[str, int]
    staged_selection_needed: bool


def plan_spell_invocation(
    state: EncounterState,
    actor: Creature,
    payload: SpellActionPayload,
) -> SpellInvocationPlan:
    """Derive target counts, candidate allocations, and staging requirements.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.spells.rules import spell_action_payload
    >>> actor = SimpleNamespace(
    ...     spellcasting=None, attributes=SimpleNamespace(level=1)
    ... )
    >>> plan = plan_spell_invocation(
    ...     SimpleNamespace(), actor,
    ...     spell_action_payload("unknown", "target"),
    ... )
    >>> (plan.spell_id, plan.selected_target_refs, plan.staged_selection_needed)
    ('unknown', ('target',), False)
    """

    spell_id = payload.spell_id
    aim_point = payload.aim_point
    spell = (
        next(
            candidate
            for candidate in actor.spellcasting.learned_spells
            if candidate.id == spell_id
        )
        if actor.spellcasting is not None
        else None
    )
    slot_level = payload.slot_level
    maximum_targets = (
        spell_max_targets(
            spell,
            slot_level,
            caster_level=actor.attributes.level,
        )
        if spell is not None
        else 1
    )
    repeat_target_allocations = bool(
        spell is not None and spell_repeats_target_allocations(spell)
    )
    require_full_target_count = bool(
        spell is not None and spell_requires_full_target_count(spell)
    )
    resource_pool_total = _resource_pool_total(spell)
    selected_targets = list(payload.target_refs)
    resource_allocation_limits: dict[str, int] = {}
    if resource_pool_total is not None and spell is not None:
        resource_allocation_limits = _healing_allocation_limits(state, actor, spell)
        selected_targets = []
        maximum_targets = len(resource_allocation_limits)
    if (
        spell is not None
        and spell_chooses_area_targets(spell)
        and aim_point is not None
    ):
        area_target_refs = tuple(
            target.target_ref
            for target in spell_area_targets(
                state,
                actor,
                spell,
                aim_point=aim_point,
            )
        )
        selects_every_occupant = bool(
            spell.definition is not None
            and spell.definition.target.count.maximum == "all"
        )
        maximum_targets = (
            len(area_target_refs)
            if selects_every_occupant
            else min(maximum_targets, len(area_target_refs))
        )
        selected_targets = list(area_target_refs[:maximum_targets])
    staged_selection_needed = bool(
        resource_pool_total is not None
        or (maximum_targets > 1 and selected_targets)
        or (
            spell is not None
            and spell_chooses_area_targets(spell)
            and len(selected_targets) > 1
        )
    )
    return SpellInvocationPlan(
        spell_id=spell_id,
        spell=spell,
        aim_point=aim_point,
        slot_level=slot_level,
        selected_target_refs=tuple(selected_targets),
        maximum_targets=maximum_targets,
        repeat_target_allocations=repeat_target_allocations,
        require_full_target_count=require_full_target_count,
        resource_pool_total=resource_pool_total,
        resource_allocation_limits=resource_allocation_limits,
        staged_selection_needed=staged_selection_needed,
    )


def automatic_spell_payload(
    state: EncounterState,
    actor: Creature,
    original_payload: SpellActionPayload,
    plan: SpellInvocationPlan,
) -> SpellActionPayload:
    """Choose a deterministic complete payload for a non-external controller.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.spells.rules import spell_action_payload
    >>> plan = SpellInvocationPlan(
    ...     spell_id="ray", spell=Spell("ray", "Ray", "TEST", 0),
    ...     aim_point=None, slot_level=None, selected_target_refs=("goblin",),
    ...     maximum_targets=2, repeat_target_allocations=True,
    ...     require_full_target_count=True, resource_pool_total=None,
    ...     resource_allocation_limits={}, staged_selection_needed=True,
    ... )
    >>> automatic_spell_payload(
    ...     SimpleNamespace(), SimpleNamespace(),
    ...     spell_action_payload("ray", "goblin"), plan,
    ... ).target_refs
    ('goblin', 'goblin')
    """

    spell = plan.spell
    assert spell is not None
    selected_targets = list(plan.selected_target_refs)
    if plan.repeat_target_allocations:
        selected_targets = [selected_targets[0]] * plan.maximum_targets
    elif plan.resource_pool_total is not None:
        allocations = _allocate_healing_pool(
            plan.resource_pool_total,
            plan.resource_allocation_limits,
        )
        return replace(
            original_payload,
            target_refs=tuple(allocations),
            aim_point=plan.aim_point,
            slot_level=plan.slot_level,
            healing_allocations=tuple(sorted(allocations.items())),
        )
    elif not spell_chooses_area_targets(spell):
        selected_targets = [
            target.target_ref
            for target in spell_action_targets(state, actor, spell)[
                : plan.maximum_targets
            ]
        ]
    return replace(
        original_payload,
        target_refs=tuple(selected_targets),
        aim_point=plan.aim_point,
        slot_level=plan.slot_level,
    )


def _resource_pool_total(spell: Spell | None) -> int | None:
    """Return the first healing pool declared by the spell, if any."""

    return next(
        (
            effect.pool
            for effect in capability_effects(
                spell.definition if spell is not None else None
            )
            if isinstance(effect, HealingEffect) and effect.pool is not None
        ),
        None,
    )


def _healing_allocation_limits(
    state: EncounterState,
    actor: Creature,
    spell: Spell,
) -> dict[str, int]:
    """Return missing effective Hit Points for every healable candidate."""

    limits: dict[str, int] = {}
    for target in spell_action_targets(state, actor, spell):
        maximum = effective_maximum_health(
            state,
            target.target_ref,
        ).value
        missing = maximum - target.creature.get_health()
        if missing > 0:
            limits[target.target_ref] = missing
    return limits


def _allocate_healing_pool(
    pool_total: int,
    limits: dict[str, int],
) -> dict[str, int]:
    """Allocate a healing pool greedily in stable candidate order."""

    remaining = pool_total
    allocations: dict[str, int] = {}
    for target_ref, limit in limits.items():
        amount = min(limit, remaining)
        if amount > 0:
            allocations[target_ref] = amount
            remaining -= amount
        if remaining == 0:
            break
    return allocations
