from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class MultiattackCount:
    kind: Literal["creature_stat", "half_spell_level"]
    stat: str | None = None
    rounding: Literal["down", "up"] = "down"


@dataclass(frozen=True)
class MultiattackRequirement:
    kind: Literal["action_used_this_turn"]
    action: str


@dataclass(frozen=True)
class MultiattackInvocation:
    kind: Literal["stat_block_action", "cast_spell"]
    name: str
    source: str | None = None
    cast_level: int | None = None


@dataclass(frozen=True)
class MultiattackStep:
    options: tuple[MultiattackInvocation, ...]
    times: int | MultiattackCount = 1
    availability: Literal["required", "optional", "use_if_available"] = "required"


@dataclass(frozen=True)
class MultiattackReplacement:
    target_kind: Literal["any_attack", "action", "step"]
    target_name: str | None
    target_step: int | None
    options: tuple[MultiattackInvocation, ...]
    replace_count: int = 1
    maximum_uses: int | Literal["unbounded"] = 1
    requirement: MultiattackRequirement | None = None


@dataclass(frozen=True)
class MultiattackPlan:
    steps: tuple[MultiattackStep, ...]
    ordering: Literal["any", "strict"] = "any"
    replacements: tuple[MultiattackReplacement, ...] = field(default_factory=tuple)
    requirement: MultiattackRequirement | None = None

    def executable_sequence(
        self,
        attack_names: set[str],
    ) -> tuple[MultiattackInvocation, ...] | None:
        sequence: list[MultiattackInvocation] = []
        for step in self.steps:
            if len(step.options) != 1:
                if step.availability == "required":
                    return None
                continue
            invocation = step.options[0]
            if (
                invocation.kind != "stat_block_action"
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
        slots: list[MultiattackStep] = []
        for step in self.steps:
            if not isinstance(step.times, int):
                return None
            available = tuple(
                option
                for option in step.options
                if option.kind == "stat_block_action" and option.name in attack_names
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
    plans: tuple[MultiattackPlan, ...]

    def executable_sequence(
        self,
        attack_names: set[str],
    ) -> tuple[MultiattackInvocation, ...] | None:
        for plan in self.plans:
            sequence = plan.executable_sequence(attack_names)
            if sequence is not None:
                return sequence
        return None

    def executable_slot_plans(
        self,
        attack_names: set[str],
    ) -> tuple[tuple[MultiattackStep, ...], ...]:
        return tuple(
            slots
            for plan in self.plans
            if (slots := plan.executable_slots(attack_names)) is not None
        )
