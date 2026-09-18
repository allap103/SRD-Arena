"""Immutable information policies, independent of YAML and client transport."""

from itertools import pairwise
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

type Group = Literal["own", "ally", "enemy"]
type Exact = Literal["exact", "hidden"]
type Inclusion = Literal["include", "omit"]
type Collection = Literal["all", "observable", "hidden"]
type Evidence = Literal["all", "demonstrated", "hidden"]


class PolicyValue(BaseModel):
    """Reject coercion and extra keys; nested policy values are immutable."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, allow_inf_nan=False
    )


class ByCreature[T](PolicyValue):
    """Select independently for the fixed perspective, teammates, and opponents."""

    own: T
    ally: T
    enemy: T

    def for_group(self, group: Group) -> T:
        """Return the policy value for one creature's relationship."""
        return (
            self.own if group == "own" else self.ally if group == "ally" else self.enemy
        )


class PerspectivePolicy(PolicyValue):
    """Choose whose perception supplies evidence."""

    knowledge_sharing: Literal["individual", "team"]


class MemoryPolicy(ByCreature[Literal["current_only", "last_known"]]):
    """Control stale dynamic facts separately from demonstrated knowledge."""

    demonstrated_facts: Literal["retain", "forget_when_unseen"]


class HealthIntervals(PolicyValue):
    """Define positive-HP fractional intervals and the full-health singleton."""

    boundaries: tuple[float, ...] = Field(min_length=2, max_length=1024)
    distinguish_full_health: bool

    @model_validator(mode="after")
    def validate_boundaries(self) -> Self:
        """Require finite, strictly increasing boundaries covering zero to one."""
        points = self.boundaries
        if (
            points[0] != 0
            or points[-1] != 1
            or any(a >= b for a, b in pairwise(points))
        ):
            raise ValueError("boundaries must increase strictly from 0 to 1")
        return self


class HealthPolicy(PolicyValue):
    """Choose exact HP, fractional intervals, or no health disclosure."""

    disclosure: ByCreature[Literal["exact", "interval", "hidden"]]
    intervals: HealthIntervals


class EffectsPolicy(PolicyValue):
    """Select instances before disclosing their duration or mechanics."""

    disclosure: ByCreature[Collection]
    duration: ByCreature[Exact]
    mechanics: ByCreature[Evidence]

    @model_validator(mode="after")
    def validate_details(self) -> Self:
        """Reject detail permissions attached to a hidden parent."""
        for group in ("own", "ally", "enemy"):
            if getattr(self.disclosure, group) == "hidden" and (
                getattr(self.duration, group) != "hidden"
                or getattr(self.mechanics, group) != "hidden"
            ):
                raise ValueError(
                    f"{group}: hidden effects require hidden duration/mechanics"
                )
        return self


class CreaturePolicy(PolicyValue):
    """Field-specific disclosure grammar for creature rows."""

    position: ByCreature[Exact]
    size: ByCreature[Exact]
    appearance: ByCreature[Literal["visible_equipment", "hidden"]]
    creature_type: ByCreature[Literal["actual", "apparent", "hidden"]]
    health: HealthPolicy
    temporary_health: ByCreature[Literal["exact", "presence", "hidden"]]
    defeated: ByCreature[Inclusion]
    armor_class: ByCreature[Exact]
    ability_scores: ByCreature[Exact]
    saving_throw_modifiers: ByCreature[Exact]
    skill_modifiers: ByCreature[Exact]
    movement: ByCreature[Exact]
    action_economy: ByCreature[Literal["exact", "availability", "hidden"]]
    resources: ByCreature[Literal["exact", "availability", "hidden"]]
    capabilities: ByCreature[Evidence]
    defenses: ByCreature[Evidence]
    conditions: ByCreature[Collection]
    concentration: ByCreature[Exact] = ByCreature[Exact](
        own="hidden", ally="hidden", enemy="hidden"
    )
    effects: EffectsPolicy
    relationships: ByCreature[Collection]


class BattlefieldPolicy(PolicyValue):
    """Select board and environmental facts."""

    dimensions: Inclusion
    terrain: Literal["all", "perceived", "explored", "hidden"]
    environment: Collection
    persistent_areas: Collection


class EncounterPolicy(PolicyValue):
    """Select public clock, order, and roster information."""

    round: Inclusion
    active_turn: Inclusion
    initiative: Literal["totals", "order", "hidden"]
    roster: Literal["all", "discovered"]


class AccumulationPolicy(PolicyValue):
    """Select learned facts independently of recent event retention."""

    damage_received: ByCreature[Exact]
    demonstrated_capabilities: bool
    demonstrated_defenses: bool


class HistoryPolicy(PolicyValue):
    """Select events and bound the public history window."""

    events: Literal["all", "perceived", "hidden"]
    recent_event_limit: int = Field(ge=0, le=10000)
    accumulated: AccumulationPolicy


class DecisionPolicy(PolicyValue):
    """Select optional context while keeping command routing mandatory."""

    context: Literal["permitted", "hidden"]
    capability_descriptions: Literal["permitted", "hidden"]


class ObservationPolicy(PolicyValue):
    """Complete version-one policy grammar; support is validated separately."""

    schema_version: int = Field(ge=1, le=1)
    name: str = Field(min_length=1, max_length=128)
    perspective: PerspectivePolicy
    visibility: ByCreature[Literal["always", "perceived"]]
    memory: MemoryPolicy
    creatures: CreaturePolicy
    battlefield: BattlefieldPolicy
    encounter: EncounterPolicy
    history: HistoryPolicy
    decisions: DecisionPolicy

    @model_validator(mode="after")
    def validate_evidence_dependencies(self) -> Self:
        """Require accumulation for any requested demonstrated facts."""
        for group in ("own", "ally", "enemy"):
            if (
                getattr(self.creatures.capabilities, group) == "demonstrated"
                or getattr(self.creatures.effects.mechanics, group) == "demonstrated"
            ) and not self.history.accumulated.demonstrated_capabilities:
                raise ValueError(
                    f"{group}: demonstrated capabilities require accumulation"
                )
            if getattr(self.creatures.defenses, group) == "demonstrated" and not (
                self.history.accumulated.demonstrated_defenses
            ):
                raise ValueError(f"{group}: demonstrated defenses require accumulation")
        return self

    def validate_support(self) -> None:
        """Reject proposed modes without complete evidence and disclosure paths.

        This initial slice keeps the established team boundary and required
        action routing. Exact allied HP is required because targeting resource
        limits can disclose missing allied health.
        """
        supported: dict[str, tuple[object, ...]] = {
            "perspective.knowledge_sharing": ("team",),
            "visibility.own": ("always",),
            "visibility.ally": ("always",),
            "visibility.enemy": ("perceived",),
            "memory.own": ("current_only",),
            "memory.ally": ("current_only",),
            "memory.enemy": ("last_known", "current_only"),
            "memory.demonstrated_facts": ("retain",),
            "battlefield.dimensions": ("include",),
            "battlefield.terrain": ("all",),
            "battlefield.environment": ("all", "hidden"),
            "battlefield.persistent_areas": ("hidden",),
            "encounter.roster": ("all",),
            "encounter.initiative": ("order", "hidden"),
            "history.events": ("perceived", "hidden"),
            "history.accumulated.demonstrated_capabilities": (False,),
            "history.accumulated.demonstrated_defenses": (False,),
            "decisions.capability_descriptions": ("hidden", "permitted"),
        }
        for group in ("own", "ally", "enemy"):
            for key, modes in {
                "position": ("exact",),
                "size": ("exact",),
                "appearance": ("visible_equipment",),
                "creature_type": ("apparent",),
                "defeated": ("include", "omit"),
                "armor_class": ("hidden",) if group == "enemy" else ("exact",),
                "ability_scores": ("hidden",),
                "saving_throw_modifiers": ("hidden",),
                "skill_modifiers": ("hidden",),
                "movement": ("hidden",) if group == "enemy" else ("hidden", "exact"),
                "action_economy": ("hidden",)
                if group == "enemy"
                else ("hidden", "exact"),
                "resources": ("hidden",) if group == "enemy" else ("hidden", "exact"),
                "capabilities": ("hidden",),
                "defenses": ("hidden",),
                "conditions": ("hidden", "observable")
                if group == "enemy"
                else ("hidden", "all"),
                "concentration": ("hidden",)
                if group == "enemy"
                else ("hidden", "exact"),
                "effects.disclosure": ("hidden",),
                "effects.duration": ("hidden",),
                "effects.mechanics": ("hidden",),
                "relationships": ("hidden",),
            }.items():
                supported[f"creatures.{key}.{group}"] = modes
            if group != "enemy":
                supported[f"creatures.health.disclosure.{group}"] = ("exact",)
                supported[f"creatures.temporary_health.{group}"] = ("exact",)
        problems = []
        for path, accepted_modes in supported.items():
            value: object = self
            for part in path.split("."):
                value = getattr(value, part)
            if value not in accepted_modes:
                problems.append(
                    f"{path}: {value!r} unsupported; supported: {accepted_modes}"
                )
        if problems:
            raise ValueError("Unsupported observation policy:\n" + "\n".join(problems))
