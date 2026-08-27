"""Describe legal compositions of actions within a creature's Multiattack."""

from dataclasses import dataclass, field
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
        attack_names: set[str],
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
                and option.name in attack_names
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
        attack_names: set[str],
    ) -> tuple[tuple[MultiattackStep, ...], ...]:
        """Return every plan whose required slots have legal options.

        >>> bite = MultiattackInvocation("stat_block_action", "Bite")
        >>> claw = MultiattackInvocation("stat_block_action", "Claw")
        >>> plans = (MultiattackPlan((MultiattackStep((bite,),),)),
        ...          MultiattackPlan((MultiattackStep((claw,),),)))
        >>> len(Multiattack(plans).executable_slot_plans({"Bite"}))
        1
        """
        return tuple(
            slots
            for plan in self.plans
            if (slots := plan.executable_slots(attack_names)) is not None
        )
