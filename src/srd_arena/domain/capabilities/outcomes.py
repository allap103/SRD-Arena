"""Outcome stages and repeated saves produced during resolution."""

from dataclasses import dataclass

from .effects import CapabilityEffect, EffectDuration


@dataclass(frozen=True)
class RepeatSave:
    trigger: str
    ability: str | None = None
    interval_amount: int | None = None
    interval_unit: str | None = None
    distance_from_source_feet: int | None = None
    effects_end_on_success: bool = True
    automatic_success_after: EffectDuration | None = None
    failure_effects: tuple[CapabilityEffect, ...] = ()
    successes_required: int = 1
    failures_required: int | None = None
    counters_need_not_be_consecutive: bool = True


@dataclass(frozen=True)
class OutcomeStage:
    effects: tuple[CapabilityEffect, ...]
    repeat_saves: tuple[RepeatSave, ...] = ()
