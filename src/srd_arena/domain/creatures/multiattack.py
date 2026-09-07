"""Describe legal compositions of actions within a creature's Multiattack."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import combinations
from typing import Literal


@dataclass(frozen=True)
class MultiattackCount:
    """Derive a repeated-step count from creature or spellcasting context."""

    kind: Literal["creature_stat", "half_spell_level"]
    stat: str | None = None
    rounding: Literal["down", "up"] = "down"


@dataclass(frozen=True)
class MultiattackRequirement:
    """Require a named action occurrence before a plan or replacement is legal."""

    kind: Literal["action_used_this_turn"]
    action: str


@dataclass(frozen=True)
class MultiattackInvocation:
    """Reference one stat-block action or spell cast used inside Multiattack."""

    kind: Literal["stat_block_action", "cast_spell"]
    name: str
    section: str = "action"
    source: str | None = None
    cast_level: int | None = None


@dataclass(frozen=True)
class MultiattackStep:
    """Offer one or more interchangeable invocations for a repeated plan step."""

    options: tuple[MultiattackInvocation, ...]
    times: int | MultiattackCount = 1
    availability: Literal["required", "optional", "use_if_available"] = "required"


@dataclass(frozen=True)
class MultiattackReplacement:
    """Allow configured invocations to replace eligible attacks or plan steps."""

    target_kind: Literal["any_attack", "action", "step"]
    target_name: str | None
    target_step: int | None
    options: tuple[MultiattackInvocation, ...]
    replace_count: int = 1
    maximum_uses: int | Literal["unbounded"] = 1
    requirement: MultiattackRequirement | None = None


type OriginSlot = tuple[MultiattackStep, int | None]
type OriginSlotPlan = tuple[OriginSlot, ...]


@dataclass(frozen=True)
class MultiattackPlan:
    """Describe one legal ordered or freely arranged Multiattack composition."""

    steps: tuple[MultiattackStep, ...]
    ordering: Literal["any", "strict"] = "any"
    replacements: tuple[MultiattackReplacement, ...] = field(default_factory=tuple)
    requirement: MultiattackRequirement | None = None

    def executable_sequence(
        self,
        attack_names: set[str],
    ) -> tuple[MultiattackInvocation, ...] | None:
        """Resolve a deterministic plan into its executable invocation sequence.

        >>> bite = MultiattackInvocation("stat_block_action", "Bite")
        >>> plan = MultiattackPlan((MultiattackStep((bite,), times=2),))
        >>> [entry.name for entry in plan.executable_sequence({"Bite"}) or ()]
        ['Bite', 'Bite']
        >>> plan.executable_sequence({"Claw"}) is None
        True
        """
        sequence: list[MultiattackInvocation] = []
        for step in self.steps:
            if len(step.options) != 1:
                if step.availability == "required":
                    return None
                continue
            invocation = step.options[0]
            if (
                invocation.kind != "stat_block_action"
                or invocation.section != "action"
                or invocation.name not in attack_names
            ):
                if step.availability == "required":
                    return None
                continue
            if not isinstance(step.times, int):
                return None
            sequence.extend([invocation] * step.times)
        return tuple(sequence) or None

    def executable_slots(
        self,
        action_names: set[str],
    ) -> tuple[MultiattackStep, ...] | None:
        """Expand a plan into slots containing only available options.

        >>> bite = MultiattackInvocation("stat_block_action", "Bite")
        >>> claw = MultiattackInvocation("stat_block_action", "Claw")
        >>> plan = MultiattackPlan((MultiattackStep((bite, claw), times=2),))
        >>> slots = plan.executable_slots({"Claw"})
        >>> [[option.name for option in slot.options] for slot in slots or ()]
        [['Claw'], ['Claw']]
        """
        slots: list[MultiattackStep] = []
        for step in self.steps:
            if not isinstance(step.times, int):
                return None
            available = tuple(
                option
                for option in step.options
                if option.kind == "stat_block_action"
                and option.section == "action"
                and option.name in action_names
            )
            if not available:
                if step.availability == "required":
                    return None
                continue
            slots.extend(
                MultiattackStep(
                    options=available,
                    availability=step.availability,
                )
                for _ in range(step.times)
            )
        return tuple(slots) or None

    def executable_slot_variants(
        self,
        action_names: set[str],
        attack_names: set[str],
    ) -> tuple[tuple[MultiattackStep, ...], ...]:
        """Expand optional replacements into independently selectable slot plans.

        Replacements are compiled before a Multiattack starts. This keeps the
        mutable turn state as a small ordered list while still allowing an
        actor to choose where a limited replacement occurs.
        """

        base = self._executable_slots_with_origins(action_names)
        if base is None:
            return ()
        variants: tuple[OriginSlotPlan, ...] = (base,)
        for replacement in self.replacements:
            expanded: list[OriginSlotPlan] = []
            for variant in variants:
                expanded.extend(
                    _expand_replacement(
                        variant,
                        replacement,
                        action_names,
                        attack_names,
                    )
                )
            variants = _unique_slot_variants(expanded)
        return tuple(tuple(slot for slot, _origin in variant) for variant in variants)

    def _executable_slots_with_origins(
        self,
        action_names: set[str],
    ) -> OriginSlotPlan | None:
        slots: list[OriginSlot] = []
        for step_index, step in enumerate(self.steps):
            if not isinstance(step.times, int):
                return None
            available = tuple(
                option
                for option in step.options
                if option.kind == "stat_block_action"
                and option.section == "action"
                and option.name in action_names
            )
            if not available:
                if step.availability == "required":
                    return None
                continue
            slots.extend(
                (
                    MultiattackStep(
                        options=available,
                        availability=step.availability,
                    ),
                    step_index,
                )
                for _ in range(step.times)
            )
        return tuple(slots) or None


@dataclass(frozen=True)
class Multiattack:
    """Collect alternative plans advertised by one creature's Multiattack entry."""

    plans: tuple[MultiattackPlan, ...]

    def executable_sequence(
        self,
        attack_names: set[str],
    ) -> tuple[MultiattackInvocation, ...] | None:
        """Return the first plan that forms a deterministic legal sequence.

        >>> bite = MultiattackInvocation("stat_block_action", "Bite")
        >>> multiattack = Multiattack((MultiattackPlan((MultiattackStep((bite,),),)),))
        >>> [entry.name for entry in multiattack.executable_sequence({"Bite"}) or ()]
        ['Bite']
        """
        for plan in self.plans:
            sequence = plan.executable_sequence(attack_names)
            if sequence is not None:
                return sequence
        return None

    def executable_slot_plans(
        self,
        action_names: set[str],
        attack_names: set[str] | None = None,
    ) -> tuple[tuple[MultiattackStep, ...], ...]:
        """Return every plan whose required slots have legal options.

        >>> bite = MultiattackInvocation("stat_block_action", "Bite")
        >>> claw = MultiattackInvocation("stat_block_action", "Claw")
        >>> plans = (MultiattackPlan((MultiattackStep((bite,),),)),
        ...          MultiattackPlan((MultiattackStep((claw,),),)))
        >>> len(Multiattack(plans).executable_slot_plans({"Bite"}))
        1
        """
        resolved_attack_names = (
            attack_names if attack_names is not None else action_names
        )
        return tuple(
            slots
            for plan in self.plans
            for slots in plan.executable_slot_variants(
                action_names,
                resolved_attack_names,
            )
        )


def _expand_replacement(
    base: OriginSlotPlan,
    replacement: MultiattackReplacement,
    action_names: set[str],
    attack_names: set[str],
) -> tuple[OriginSlotPlan, ...]:
    """Return the unchanged plan plus every legal use of one replacement."""

    available_options = tuple(
        option
        for option in replacement.options
        if option.kind == "stat_block_action"
        and option.section == "action"
        and option.name in action_names
    )
    if not available_options or replacement.requirement is not None:
        return (base,)
    maximum = (
        len(base) // replacement.replace_count
        if replacement.maximum_uses == "unbounded"
        else replacement.maximum_uses
    )
    variants: list[OriginSlotPlan] = [base]
    frontier = [base]
    for _ in range(maximum):
        next_frontier: list[OriginSlotPlan] = []
        for variant in frontier:
            eligible = [
                index
                for index, (slot, origin) in enumerate(variant)
                if origin is not None
                and _replacement_matches(
                    replacement,
                    slot,
                    origin,
                    attack_names,
                )
            ]
            for selected in combinations(eligible, replacement.replace_count):
                first = selected[0]
                selected_set = set(selected)
                replacement_slot = (
                    MultiattackStep(options=available_options),
                    None,
                )
                candidate = tuple(
                    replacement_slot if index == first else entry
                    for index, entry in enumerate(variant)
                    if index not in selected_set or index == first
                )
                next_frontier.append(candidate)
        if not next_frontier:
            break
        variants.extend(next_frontier)
        frontier = list(_unique_slot_variants(next_frontier))
    return _unique_slot_variants(variants)


def _replacement_matches(
    replacement: MultiattackReplacement,
    slot: MultiattackStep,
    origin: int,
    attack_names: set[str],
) -> bool:
    if replacement.target_kind == "step":
        return replacement.target_step == origin
    if replacement.target_kind == "action":
        return any(option.name == replacement.target_name for option in slot.options)
    return any(option.name in attack_names for option in slot.options)


def _unique_slot_variants(
    variants: Iterable[OriginSlotPlan],
) -> tuple[OriginSlotPlan, ...]:
    unique: list[OriginSlotPlan] = []
    seen: set[tuple[tuple[tuple[str, str], ...], ...]] = set()
    for variant in variants:
        key = tuple(
            tuple((option.kind, option.name) for option in slot.options)
            for slot, _origin in variant
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(variant)
    return tuple(unique)
