"""Read-only application observations for game clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping, cast

from srd_arena.domain.geometry import (
    Position,
    Vector2D,
    build_directional_area,
    build_point_cube_area,
    build_radius_area,
    serialize_area,
)
from srd_arena.domain.spells.rules import (
    parse_spell_action_slot,
    parse_spell_action_value,
    spell_area_shape,
    spell_range_squares,
)
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
    source_id: str | None = None
    source_label: str | None = None
    source_level: int | None = None
    resource_level: int | None = None
    target_ref: str | None = None
    aim_point: tuple[float, float] | None = None
    area_preview: dict[str, object] | None = None

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
    id: str
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
class AttributeObservation:
    level: int
    strength: int
    dexterity: int
    constitution: int
    wisdom: int
    intelligence: int
    charisma: int
    proficiency_bonus: int


@dataclass(frozen=True)
class InventoryItemObservation:
    item_id: str
    name: str


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
    armor_class: int
    attributes: AttributeObservation
    inventory: tuple[InventoryItemObservation, ...]


@dataclass(frozen=True)
class OngoingEffectObservation:
    kind: str
    polarity: str
    applied_by_ref: str | None
    definition_id: str
    target_refs: tuple[str, ...]
    label: str


@dataclass(frozen=True)
class TargetResourceLimitObservation:
    target_ref: str
    maximum: int


@dataclass(frozen=True)
class TargetResourceAllocationObservation:
    target_ref: str
    amount: int


@dataclass(frozen=True)
class TargetingObservation:
    source_id: str
    source_label: str
    selected_target_refs: tuple[str, ...]
    maximum_targets: int
    repeat_target_allocations: bool
    require_full_target_count: bool
    resource_pool_total: int | None
    resource_allocations: tuple[TargetResourceAllocationObservation, ...]
    resource_limits: tuple[TargetResourceLimitObservation, ...]


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
    targeting: TargetingObservation | None

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

    scene_view = session.get_scene_view()
    state = session.encounter_state
    scene = _observe_scene(scene_view, state)
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


def _observe_scene(scene: SceneView, state: Any | None) -> SceneObservation:
    return SceneObservation(
        scene_id=scene.scene_id,
        scene_text=scene.scene_text,
        action_details=tuple(
            _observe_action(action, state) for action in scene.action_details
        ),
    )


def _observe_action(action: ActionView, state: Any | None) -> ActionObservation:
    reason_messages = action.unavailable_reasons or (
        (action.unavailable_reason,) if action.unavailable_reason else ()
    )
    reason_codes = action.unavailable_codes or tuple(
        action.availability for _ in reason_messages
    )
    semantics = _action_semantics(action, state)
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
        **semantics,
    )


def _action_semantics(
    action: ActionView,
    state: Any | None,
) -> dict[str, Any]:
    if state is None:
        return {}
    creature_state = state.creatures.get(action.creature_ref)
    if creature_state is None:
        return {}
    creature = creature_state.creature
    if action.kind in {"spell", "toggle_spell_target"}:
        source_id, target_ref, aim_point = _spell_action_parts(action)
        spell = _find_spell(creature, source_id)
        return {
            "source_id": source_id,
            "source_label": spell.name if spell is not None else source_id,
            "source_level": spell.level if spell is not None else None,
            "resource_level": (
                parse_spell_action_slot(action.value)
                if action.kind == "spell" and isinstance(action.value, str)
                else None
            ),
            "target_ref": target_ref,
            "aim_point": aim_point,
            "area_preview": _spell_area_preview(state, creature_state, spell, aim_point),
        }
    if action.kind == "stat_block":
        definition = creature.stat_block_actions.get(action.preferred_attack_name or "")
        return {
            "source_id": action.preferred_attack_name,
            "source_label": action.preferred_attack_name,
            "target_ref": _direct_target_ref(action.value),
            "area_preview": _stat_block_area_preview(
                state,
                creature_state,
                definition,
            ),
        }
    if action.kind in {"attack", "grapple", "opportunity_attack"}:
        return {"target_ref": _direct_target_ref(action.value)}
    return {}


def _spell_action_parts(
    action: ActionView,
) -> tuple[str | None, str | None, tuple[float, float] | None]:
    if action.kind == "spell" and isinstance(action.value, str):
        return parse_spell_action_value(action.value)
    return (
        action.source_trigger_id,
        action.value if isinstance(action.value, str) else None,
        None,
    )


def _direct_target_ref(
    value: str | int | tuple[float, float] | None,
) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return f"participant:{value}"
    return None


def _find_spell(creature: Any, spell_id: str | None) -> Any | None:
    if spell_id is None or creature.spellcasting is None:
        return None
    return next(
        (
            spell
            for spell in creature.spellcasting.learned_spells
            if spell.id == spell_id
        ),
        None,
    )


def _spell_area_preview(
    state: Any,
    creature_state: Any,
    spell: Any | None,
    aim_point: tuple[float, float] | None,
) -> dict[str, object] | None:
    if spell is None or aim_point is not None:
        return None
    grid = state.definition.grid
    if spell.geometry_mode == "point_area":
        if spell.area_size_feet is None:
            return None
        size_squares = int(
            grid.distance_from_feet(spell.area_size_feet, minimum=1)
        )
        area = (
            build_point_cube_area(Position(0, 0), size_squares, grid)
            if spell_area_shape(spell) == "cube"
            else build_radius_area(Position(0, 0), size_squares, grid)
        )
        return serialize_area(area)
    if spell.geometry_mode != "directional_area":
        return None
    length = spell_range_squares(spell, grid)
    if length is None:
        return None
    return serialize_area(
        build_directional_area(
            spell.range_data.get("type"),
            Position(creature_state.position.x, creature_state.position.y),
            Vector2D(1.0, 0.0),
            length,
            grid,
            coverage_threshold=(
                state.geometry_config.directional_area_cell_coverage_threshold
            ),
        )
    )


def _stat_block_area_preview(
    state: Any,
    creature_state: Any,
    definition: Any | None,
) -> dict[str, object] | None:
    target = getattr(definition, "target", None)
    shape = getattr(target, "shape", None)
    size_feet = getattr(target, "size_feet", None)
    if (
        getattr(target, "kind", None) != "area"
        or not isinstance(shape, str)
        or not isinstance(size_feet, int)
    ):
        return None
    grid = state.definition.grid
    width_feet = getattr(target, "width_feet", None)
    width_squares = max(
        1.0,
        (width_feet if isinstance(width_feet, int) else grid.square_size_feet)
        / grid.square_size_feet,
    )
    return serialize_area(
        build_directional_area(
            shape,
            Position(creature_state.position.x, creature_state.position.y),
            Vector2D(1.0, 0.0),
            int(grid.distance_from_feet(size_feet, minimum=1)),
            grid,
            width_squares=width_squares,
            coverage_threshold=(
                state.geometry_config.directional_area_cell_coverage_threshold
            ),
        )
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
            id=str(decision["frame_id"]),
            kind=str(decision["kind"]),
            creature_ref=str(decision["creature_ref"]),
        ),
        creatures=tuple(
            _observe_creature(session, state, creature_ref, creature)
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
        targeting=_observe_targeting(state),
    )


def _observe_targeting(state: Any) -> TargetingObservation | None:
    pending = state.pending_spell_cast
    if pending is None:
        return None
    actor = state.creatures[state.current_decision().creature_ref].creature
    spell = (
        next(
            (
                spell
                for spell in actor.spellcasting.learned_spells
                if spell.id == pending.spell_id
            ),
            None,
        )
        if actor.spellcasting is not None
        else None
    )
    return TargetingObservation(
        source_id=pending.spell_id,
        source_label=spell.name if spell is not None else pending.spell_id,
        selected_target_refs=tuple(pending.selected_target_refs),
        maximum_targets=pending.maximum_targets,
        repeat_target_allocations=pending.repeat_target_allocations,
        require_full_target_count=pending.require_full_target_count,
        resource_pool_total=pending.resource_pool_total,
        resource_allocations=tuple(
            TargetResourceAllocationObservation(target_ref=target_ref, amount=amount)
            for target_ref, amount in pending.resource_allocations.items()
        ),
        resource_limits=tuple(
            TargetResourceLimitObservation(target_ref=target_ref, maximum=maximum)
            for target_ref, maximum in pending.resource_allocation_limits.items()
        ),
    )


def _observe_creature(
    session: Session,
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
    domain_creature = state.creatures[creature_ref].creature
    attributes = domain_creature.attributes
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
        armor_class=int(creature["armor_class"]),
        attributes=AttributeObservation(
            level=attributes.level,
            strength=attributes.strength,
            dexterity=attributes.dexterity,
            constitution=attributes.constitution,
            wisdom=attributes.wisdom,
            intelligence=attributes.intelligence,
            charisma=attributes.charisma,
            proficiency_bonus=attributes.proficiency_bonus,
        ),
        inventory=tuple(
            InventoryItemObservation(
                item_id=item_id,
                name=(
                    session.item_templates[item_id].name
                    if item_id in session.item_templates
                    else item_id
                ),
            )
            for item_id in domain_creature.inventory.items
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
