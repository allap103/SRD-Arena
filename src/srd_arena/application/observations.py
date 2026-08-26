"""Read-only application observations for game clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping, cast

from srd_arena.runtime.models import ActionView, SceneView
from srd_arena.runtime.session import Session


@dataclass(frozen=True)
class ActionReasonObservation:
    code: str
    message: str


@dataclass(frozen=True)
class ActionObservation:
    """A stable selectable option advertised at one decision point."""

    id: str
    label: str
    kind: str
    creature_ref: str
    value: str | int | tuple[float, float] | None = None
    cost: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    enabled: bool = True
    availability: Literal["available", "unavailable", "unimplemented"] = "available"
    reasons: tuple[ActionReasonObservation, ...] = ()
    source_trigger_id: str | None = None
    preferred_attack_type: str | None = None
    preferred_attack_name: str | None = None

    @property
    def unavailable_reason(self) -> str | None:
        return "\n".join(reason.message for reason in self.reasons) or None

    @property
    def unavailable_reasons(self) -> tuple[str, ...]:
        return tuple(reason.message for reason in self.reasons)


@dataclass(frozen=True)
class SceneObservation:
    scene_id: str
    scene_text: str | None
    action_details: tuple[ActionObservation, ...]


@dataclass(frozen=True)
class GridObservation:
    width: int
    height: int


@dataclass(frozen=True)
class PositionObservation:
    x: int
    y: int


@dataclass(frozen=True)
class DecisionObservation:
    kind: str
    creature_ref: str


@dataclass(frozen=True)
class InitiativeObservation:
    creature_ref: str
    total: int


@dataclass(frozen=True)
class SpellSlotObservation:
    level: int
    remaining: int
    maximum: int


@dataclass(frozen=True)
class FeatureActionObservation:
    feature_id: str
    label: str
    economy: str


@dataclass(frozen=True)
class CreatureObservation:
    creature_ref: str
    creature_id: str
    name: str
    label: str
    token_image: str | None
    team_id: str
    position: PositionObservation
    health: int
    max_health: int
    is_alive: bool
    action_available: bool
    bonus_action_available: bool
    reaction_available: bool
    attacks_remaining: int
    attacks_per_attack_action: int
    movement_remaining: int
    movement_total: int
    movement_remaining_feet: int
    movement_total_feet: int
    effective_conditions: tuple[str, ...]
    spell_slots: tuple[SpellSlotObservation, ...]
    feature_actions: tuple[FeatureActionObservation, ...]


@dataclass(frozen=True)
class OngoingEffectObservation:
    kind: str
    polarity: str
    applied_by_ref: str | None
    definition_id: str
    target_refs: tuple[str, ...]
    label: str


@dataclass(frozen=True)
class EncounterObservation:
    encounter_id: str
    grid: GridObservation
    round_number: int
    decision: DecisionObservation
    creatures: tuple[CreatureObservation, ...]
    initiative: tuple[InitiativeObservation, ...]
    ongoing_effects: tuple[OngoingEffectObservation, ...]
    team_ids: tuple[str, ...]

    def creature(self, creature_ref: str) -> CreatureObservation:
        """Return a combatant by its stable encounter reference."""

        return next(
            creature
            for creature in self.creatures
            if creature.creature_ref == creature_ref
        )


@dataclass(frozen=True)
class TransitionObservation:
    message: str


@dataclass(frozen=True)
class GameObservation:
    """Everything a client may inspect about the current decision point."""

    scene: SceneObservation
    encounter: EncounterObservation | None
    transition: TransitionObservation | None
    requires_automatic_advance: bool


def observe_session(session: Session) -> GameObservation:
    """Translate mutable engine state into a frontend-neutral snapshot."""

    scene = _observe_scene(session.get_scene_view())
    state = session.encounter_state
    transition = (
        TransitionObservation(message=session.pending_scene_transition.message)
        if session.pending_scene_transition is not None
        else None
    )
    return GameObservation(
        scene=scene,
        encounter=_observe_encounter(session) if state is not None else None,
        transition=transition,
        requires_automatic_advance=(
            transition is None
            and state is not None
            and state.requires_automatic_advance()
        ),
    )


def _observe_scene(scene: SceneView) -> SceneObservation:
    return SceneObservation(
        scene_id=scene.scene_id,
        scene_text=scene.scene_text,
        action_details=tuple(
            _observe_action(action) for action in scene.action_details
        ),
    )


def _observe_action(action: ActionView) -> ActionObservation:
    reason_messages = action.unavailable_reasons or (
        (action.unavailable_reason,) if action.unavailable_reason else ()
    )
    reason_codes = action.unavailable_codes or tuple(
        action.availability for _ in reason_messages
    )
    return ActionObservation(
        id=action.id,
        label=action.label,
        kind=action.kind,
        creature_ref=action.creature_ref,
        value=action.value,
        cost=MappingProxyType(dict(action.cost)),
        enabled=action.enabled,
        availability=action.availability,
        reasons=tuple(
            ActionReasonObservation(code=code, message=message)
            for code, message in zip(reason_codes, reason_messages, strict=False)
        ),
        source_trigger_id=action.source_trigger_id,
        preferred_attack_type=action.preferred_attack_type,
        preferred_attack_name=action.preferred_attack_name,
    )


def _observe_encounter(session: Session) -> EncounterObservation:
    state = session.encounter_state
    if state is None:
        raise RuntimeError("Cannot observe an encounter before it has started.")
    exported = cast(dict[str, Any], state.export_state())
    creatures = cast(dict[str, dict[str, Any]], exported["creatures"])
    grid = cast(dict[str, int], exported["grid"])
    decision = cast(dict[str, Any], exported["decision"])
    initiative = cast(list[dict[str, Any]], exported["initiative"])
    ongoing_effects = cast(list[dict[str, Any]], exported["ongoing_effects"])

    return EncounterObservation(
        encounter_id=str(exported["encounter_id"]),
        grid=GridObservation(width=grid["width"], height=grid["height"]),
        round_number=int(exported["round_number"]),
        decision=DecisionObservation(
            kind=str(decision["kind"]),
            creature_ref=str(decision["creature_ref"]),
        ),
        creatures=tuple(
            _observe_creature(state, creature_ref, creature)
            for creature_ref, creature in creatures.items()
        ),
        initiative=tuple(
            InitiativeObservation(
                creature_ref=str(entry["creature_ref"]),
                total=int(entry["total"]),
            )
            for entry in initiative
        ),
        ongoing_effects=tuple(_observe_effect(effect) for effect in ongoing_effects),
        team_ids=tuple(team.id for team in session.current_encounter.teams),
    )


def _observe_creature(
    state: Any,
    creature_ref: str,
    creature: dict[str, Any],
) -> CreatureObservation:
    position = cast(dict[str, int], creature["position"])
    slots_max = cast(dict[str, int], creature["spell_slots_max"])
    slots_remaining = cast(dict[str, int], creature["spell_slots_remaining"])
    effective_conditions = cast(list[dict[str, Any]], creature["effective_conditions"])
    feature_definitions = state.creatures[
        creature_ref
    ].creature.combat_profile.feature_actions
    return CreatureObservation(
        creature_ref=creature_ref,
        creature_id=str(creature["creature_id"]),
        name=str(creature["name"]),
        label=str(creature["label"]),
        token_image=cast(str | None, creature["token_image"]),
        team_id=str(creature["team_id"]),
        position=PositionObservation(x=position["x"], y=position["y"]),
        health=int(creature["health"]),
        max_health=int(creature["max_health"]),
        is_alive=bool(creature["is_alive"]),
        action_available=bool(creature["action_available"]),
        bonus_action_available=bool(creature["bonus_action_available"]),
        reaction_available=bool(creature["reaction_available"]),
        attacks_remaining=int(creature["attacks_remaining"]),
        attacks_per_attack_action=int(creature["attacks_per_attack_action"]),
        movement_remaining=int(creature["movement_remaining"]),
        movement_total=int(creature["movement_total"]),
        movement_remaining_feet=int(creature["movement_remaining_feet"]),
        movement_total_feet=int(creature["movement_total_feet"]),
        effective_conditions=tuple(
            dict.fromkeys(
                str(condition["condition"]) for condition in effective_conditions
            )
        ),
        spell_slots=tuple(
            SpellSlotObservation(
                level=int(level),
                remaining=int(slots_remaining.get(level, maximum)),
                maximum=maximum,
            )
            for level, maximum in sorted(
                slots_max.items(), key=lambda item: int(item[0])
            )
            if maximum > 0
        ),
        feature_actions=tuple(
            FeatureActionObservation(
                feature_id=definition.feature_id,
                label=definition.label,
                economy=definition.economy,
            )
            for definition in feature_definitions.values()
        ),
    )


def _observe_effect(effect: dict[str, Any]) -> OngoingEffectObservation:
    source = cast(dict[str, Any], effect["source"])
    parameters = cast(dict[str, Any], effect["parameters"])
    definition_id = str(source["definition_id"])
    explicit_label = parameters.get("effect_label")
    label = (
        explicit_label
        if isinstance(explicit_label, str) and explicit_label.strip()
        else definition_id.replace("_", " ").replace("-", " ").title()
    )
    return OngoingEffectObservation(
        kind=str(effect["kind"]),
        polarity=str(effect["polarity"]),
        applied_by_ref=cast(str | None, source.get("applied_by_ref")),
        definition_id=definition_id,
        target_refs=tuple(str(ref) for ref in effect["target_refs"]),
        label=label,
    )
