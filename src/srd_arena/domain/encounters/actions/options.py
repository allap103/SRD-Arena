from __future__ import annotations

from typing import TYPE_CHECKING

from ...capabilities import (
    ConditionEffect,
    DamageReductionEffect,
    DamageResistanceEffect,
    HealingEffect,
    RollModifierEffect,
    TemporaryHitPointsEffect,
    capability_area_size_feet,
    capability_area_shape,
    capability_chooses_area_targets,
    capability_effects,
    capability_geometry_mode,
    capability_removable_conditions,
    capability_removable_effect_kinds,
    capability_remove_effect_selection,
    capability_supports_resource_scaling,
    capability_target_disposition,
    primary_effects,
)
from ...creatures import Creature, Spellcasting
from ...effects.conditions import CombatTrait
from ...geometry import (
    AreaOfEffect,
    Position,
    Vector2D,
    build_directional_area,
    build_point_cube_area,
    build_radius_area,
    grid_distance_between,
    vector_between_positions,
)
from ..models import ActionCost, EncounterAction
from ...spells.definitions import Spell
from ...capabilities.execution import CapabilityTargetContext
from ...spells.rules import (
    spell_action_economy,
    spell_action_id,
    spell_action_label,
    spell_action_value,
    spell_cast_block_reason,
    spell_range_squares,
    spell_targets_self_only,
)
from ...spells.rules import parse_spell_action_condition, parse_spell_action_value
from ...spells.rules import parse_spell_action_damage_type
from ...spells.rules import parse_spell_action_ability

if TYPE_CHECKING:
    from ..encounter import EncounterState


def available_actions(self: EncounterState) -> list[EncounterAction]:
    decision = self.current_decision()
    if self._creature_controller(decision.creature_ref) != "external":
        return []
    if decision.kind == "reroll_dice":
        return self._reroll_damage_actions()
    if decision.kind == "reaction":
        return self._reaction_actions()
    if decision.kind == "spell_targets":
        return spell_target_selection_actions(self, decision.creature_ref)
    return self._available_creature_actions(decision.creature_ref)


def available_feature_actions(
    self: EncounterState,
    creature: Creature,
) -> list[EncounterAction]:
    creature_ref = self.current_decision().creature_ref
    actions: list[EncounterAction] = []
    for feature_id, definition in creature.combat_profile.feature_actions.items():
        if definition.economy == "reaction":
            continue
        action_cost = ActionCost(
            bonus_action=1 if definition.economy == "bonus_action" else 0,
            action=1 if definition.economy == "action" else 0,
            reaction=1 if definition.economy == "reaction" else 0,
        )
        actions.append(
            EncounterAction(
                definition.label,
                "feature",
                feature_id,
                id=f"{creature_ref}-feature-{feature_id.replace('_', '-')}",
                creature_ref=creature_ref,
                cost=action_cost,
            )
        )
    return actions


def available_spell_actions(
    self: EncounterState,
    actor: Creature,
) -> list[EncounterAction]:
    spellcasting = actor.spellcasting
    creature_ref = self.current_decision().creature_ref
    if spellcasting is None:
        return []
    actions: list[EncounterAction] = []
    for spell in spellcasting.learned_spells:
        cost = self._spell_action_cost(spell)
        if capability_geometry_mode(spell.definition) in {
            "directional_area",
            "point_area",
        }:
            _append_spell_action_variants(
                actions,
                spellcasting,
                spell,
                EncounterAction(
                    spell_action_label(spell, actor_ref=creature_ref),
                    "spell",
                    spell_action_value(spell.id),
                    id=spell_action_id(spell),
                    creature_ref=creature_ref,
                    cost=cost,
                ),
            )
            continue
        targets = self._spell_action_targets(actor, spell)
        shared_effects = capability_effects(spell.definition)
        conditions = tuple(
            effect.condition
            for effect in primary_effects(spell.definition)
            if isinstance(effect, ConditionEffect)
        )
        resistance = next(
            (
                effect
                for effect in shared_effects
                if isinstance(effect, DamageResistanceEffect)
            ),
            None,
        )
        reduction = next(
            (
                effect
                for effect in shared_effects
                if isinstance(effect, DamageReductionEffect)
            ),
            None,
        )
        for target in targets:
            removal_choices = _spell_removal_choices(self, target.target_ref, spell)
            selections = (
                tuple(choice for choice, _label in removal_choices)
                if capability_removable_effect_kinds(spell.definition)
                and capability_remove_effect_selection(spell.definition) != "all"
                else conditions
                if spell.definition is not None
                and spell.definition.condition_selection == "choose_one"
                else (None,)
            )
            damage_type_selections: tuple[str | None, ...] = (
                (
                    resistance.damage_types
                    if resistance is not None and resistance.selection == "choose_one"
                    else reduction.damage_types
                    if reduction is not None and reduction.selection == "choose_one"
                    else ()
                )
                if resistance is not None
                and resistance.selection == "choose_one"
                or reduction is not None
                and reduction.selection == "choose_one"
                else (None,)
            )
            ability_choices = tuple(
                ability
                for effect in shared_effects
                if isinstance(effect, RollModifierEffect)
                for ability in effect.ability_options
            )
            ability_selections: tuple[str | None, ...] = (
                ability_choices if ability_choices else (None,)
            )
            for selection in selections:
                for damage_type_selection in damage_type_selections:
                    for ability_selection in ability_selections:
                        _append_spell_option(
                            actions,
                            spellcasting,
                            spell,
                            target.target_ref,
                            creature_ref,
                            cost,
                            selection,
                            removal_choices,
                            damage_type_selection,
                            ability_selection,
                        )
        if not targets:
            _append_spell_action_variants(
                actions,
                spellcasting,
                spell,
                EncounterAction(
                    spell_action_label(spell, actor_ref=creature_ref),
                    "spell",
                    spell_action_value(spell.id),
                    id=spell_action_id(spell),
                    creature_ref=creature_ref,
                    cost=cost,
                ),
            )
    return actions


def _append_spell_option(
    actions: list[EncounterAction],
    spellcasting: Spellcasting,
    spell: Spell,
    target_ref: str,
    creature_ref: str,
    cost: ActionCost,
    selection: str | None,
    removal_choices: tuple[tuple[str, str], ...],
    damage_type_selection: str | None,
    ability_selection: str | None,
) -> None:
    selection_display = next(
        (label for choice, label in removal_choices if choice == selection),
        selection.title() if isinstance(selection, str) else "",
    )
    selection_label = f" ({selection_display})" if isinstance(selection, str) else ""
    if damage_type_selection is not None:
        selection_label = f" ({damage_type_selection.title()})"
    if ability_selection is not None:
        selection_label = f" ({ability_selection.title()})"
    selected_id = selection or damage_type_selection or ability_selection
    selection_id = (
        f"-{selected_id.replace(':', '-').replace('@', '-')}" if selected_id else ""
    )
    _append_spell_action_variants(
        actions,
        spellcasting,
        spell,
        EncounterAction(
            spell_action_label(spell, actor_ref=creature_ref) + selection_label,
            "spell",
            spell_action_value(
                spell.id,
                target_ref,
                selected_condition=selection,
                selected_damage_type=damage_type_selection,
                selected_ability=ability_selection,
            ),
            id=spell_action_id(spell, target_ref=target_ref) + selection_id,
            creature_ref=creature_ref,
            cost=cost,
        ),
    )


def _append_spell_action_variants(
    actions: list[EncounterAction],
    spellcasting: Spellcasting,
    spell: Spell,
    action: EncounterAction,
) -> None:
    actions.append(action)
    if spell.level == 0:
        return
    if not capability_supports_resource_scaling(spell.definition):
        return
    spell_id, target_ref, aim_point = parse_spell_action_value(str(action.value))
    selected_condition = parse_spell_action_condition(str(action.value))
    selected_damage_type = parse_spell_action_damage_type(str(action.value))
    selected_ability = parse_spell_action_ability(str(action.value))
    for slot_level in sorted(spellcasting.spell_slots_remaining):
        if slot_level <= spell.level:
            continue
        if spellcasting.spell_slots_remaining[slot_level] <= 0:
            continue
        actions.append(
            EncounterAction(
                f"{action.label} (Level {slot_level})",
                action.kind,
                spell_action_value(
                    spell_id,
                    target_ref=target_ref,
                    aim_point=aim_point,
                    selected_condition=selected_condition,
                    selected_damage_type=selected_damage_type,
                    selected_ability=selected_ability,
                    slot_level=slot_level,
                ),
                id=f"{action.id}-level-{slot_level}",
                creature_ref=action.creature_ref,
                cost=action.cost,
            )
        )


def spell_target_selection_actions(
    state: EncounterState,
    creature_ref: str,
) -> list[EncounterAction]:
    pending = state.pending_spell_cast
    if pending is None:
        return []
    actor = state.creatures[creature_ref].creature
    spell = (
        next(
            candidate
            for candidate in actor.spellcasting.learned_spells
            if candidate.id == pending.spell_id
        )
        if actor.spellcasting is not None
        else None
    )
    if spell is None:
        return []
    actions: list[EncounterAction] = []
    _spell_id, _target_ref, aim_point = parse_spell_action_value(
        str(pending.action.value)
    )
    candidates = (
        state._spell_area_targets(actor, spell, aim_point=aim_point)
        if capability_chooses_area_targets(spell.definition)
        else tuple(state._spell_action_targets(actor, spell))
    )
    if pending.resource_pool_total is not None:
        for target in candidates:
            limit = pending.resource_allocation_limits.get(target.target_ref)
            if limit is None:
                continue
            current = pending.resource_allocations.get(target.target_ref, 0)
            actions.append(
                EncounterAction(
                    f"Allocate healing to {target.target_label}",
                    "set_spell_resource_allocation",
                    f"{target.target_ref}~{current}",
                    id=(
                        f"{creature_ref}-spell-allocation-"
                        f"{target.target_ref.replace(':', '-')}"
                    ),
                    creature_ref=creature_ref,
                    source_trigger_id=pending.spell_id,
                )
            )
        allocated = sum(pending.resource_allocations.values())
        if allocated > 0:
            actions.append(
                EncounterAction(
                    f"Cast {spell.name} ({allocated}/{pending.resource_pool_total} HP)",
                    "confirm_spell_targets",
                    id=f"{creature_ref}-confirm-{spell.id}",
                    creature_ref=creature_ref,
                    cost=pending.action.cost,
                )
            )
        actions.append(
            EncounterAction(
                f"Cancel {spell.name}",
                "cancel_spell_targets",
                id=f"{creature_ref}-cancel-{spell.id}",
                creature_ref=creature_ref,
            )
        )
        return actions
    for target in candidates:
        if pending.repeat_target_allocations:
            selected_count = pending.selected_target_refs.count(target.target_ref)
            if selected_count:
                actions.append(
                    EncounterAction(
                        f"Remove {target.target_label} ({selected_count})",
                        "toggle_spell_target",
                        target.target_ref,
                        id=(
                            f"{creature_ref}-spell-target-"
                            f"{target.target_ref.replace(':', '-')}-remove"
                        ),
                        creature_ref=creature_ref,
                        source_trigger_id=pending.spell_id,
                    )
                )
            if len(pending.selected_target_refs) < pending.maximum_targets:
                actions.append(
                    EncounterAction(
                        f"Add {target.target_label} ({selected_count + 1})",
                        "toggle_spell_target",
                        target.target_ref,
                        id=(
                            f"{creature_ref}-spell-target-"
                            f"{target.target_ref.replace(':', '-')}-add"
                        ),
                        creature_ref=creature_ref,
                        source_trigger_id=pending.spell_id,
                    )
                )
            continue
        selected = target.target_ref in pending.selected_target_refs
        if (
            not selected
            and len(pending.selected_target_refs) >= pending.maximum_targets
        ):
            continue
        actions.append(
            EncounterAction(
                ("Remove " if selected else "Add ") + target.target_label,
                "toggle_spell_target",
                target.target_ref,
                id=(
                    f"{creature_ref}-spell-target-{target.target_ref.replace(':', '-')}"
                ),
                creature_ref=creature_ref,
                source_trigger_id=pending.spell_id,
            )
        )
    can_confirm = bool(pending.selected_target_refs) and (
        not pending.require_full_target_count
        or len(pending.selected_target_refs) == pending.maximum_targets
    )
    if can_confirm:
        actions.append(
            EncounterAction(
                f"Cast {spell.name} ({len(pending.selected_target_refs)}/"
                f"{pending.maximum_targets} targets)",
                "confirm_spell_targets",
                id=f"{creature_ref}-confirm-{spell.id}",
                creature_ref=creature_ref,
                cost=pending.action.cost,
            )
        )
    actions.append(
        EncounterAction(
            f"Cancel {spell.name}",
            "cancel_spell_targets",
            id=f"{creature_ref}-cancel-{spell.id}",
            creature_ref=creature_ref,
        )
    )
    return [
        action
        for action in actions
        if state.combat_rules.action_eligibility(
            state,
            creature_ref,
            action,
        ).allowed
    ]


def feature_action_available(self: EncounterState, actor: Creature, definition) -> bool:
    if definition.economy == "bonus_action" and not self.active_bonus_action_available:
        return False
    if definition.economy == "action" and self.active_actions_remaining <= 0:
        return False
    if definition.economy == "reaction" and not self.active_reaction_available:
        return False
    return actor.feature_uses_remaining.get(definition.feature_id, 0) > 0


def spell_action_cost(self: EncounterState, spell: Spell) -> ActionCost:
    economy = spell_action_economy(spell)
    return ActionCost(
        action=economy.action,
        bonus_action=economy.bonus_action,
        reaction=economy.reaction,
    )


def spell_cast_block_reason_for(
    self: EncounterState,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
    cast_level: int | None = None,
) -> str | None:
    return spell_cast_block_reason(
        spellcasting,
        spell,
        spell_action_economy(spell),
        action_available=self.active_magic_actions_remaining > 0,
        bonus_action_available=self.active_bonus_action_available,
        reaction_available=self.active_reaction_available,
        cast_level=cast_level,
    )


def spell_targets_self_only_for(self: EncounterState, spell: Spell) -> bool:
    return capability_geometry_mode(
        spell.definition
    ) == "self_only" or spell_targets_self_only(spell)


def spell_range_squares_for(
    self: EncounterState, spell: Spell, creature: Creature
) -> int | None:
    return spell_range_squares(spell, self.definition.grid)


def spell_action_targets(
    self: EncounterState,
    actor: Creature,
    spell: Spell,
) -> list[CapabilityTargetContext]:
    creature_ref = self.current_decision().creature_ref
    creature_position = self._creature_position(creature_ref)
    if capability_removable_effect_kinds(spell.definition) and not (
        any(
            isinstance(effect, (HealingEffect, TemporaryHitPointsEffect))
            for effect in capability_effects(spell.definition)
        )
    ):
        restoration_targets: list[CapabilityTargetContext] = []
        max_range = self._spell_range_squares(spell, actor)
        for target_ref, target_state in self.creatures.items():
            if not target_state.is_alive:
                continue
            if (
                max_range is not None
                and grid_distance_between(creature_position, target_state.position)
                > max_range
            ):
                continue
            target = self._spell_target_context(actor, target_ref)
            if target is not None and _spell_removal_choices(self, target_ref, spell):
                restoration_targets.append(target)
        return restoration_targets
    if capability_geometry_mode(spell.definition) == "point_area":
        max_range = self._spell_range_squares(spell, actor)
        if max_range is None:
            return []
        return [
            target
            for target_ref, target_state in self.creatures.items()
            if target_state.is_alive
            and self._creatures_are_opponents(creature_ref, target_ref)
            and grid_distance_between(creature_position, target_state.position)
            <= max_range
            and (target := self._spell_target_context(actor, target_ref)) is not None
        ]
    if self._spell_targets_self_only(spell):
        target = self._spell_target_context(actor, creature_ref)
        if target is None:
            return []
        if _spell_removal_choices(self, creature_ref, spell):
            return [target]
        return []

    max_range = self._spell_range_squares(spell, actor)
    targets: list[CapabilityTargetContext] = []
    for target_ref, target_state in self.creatures.items():
        if not target_state.is_alive:
            continue
        disposition = capability_target_disposition(spell.definition) or "enemy"
        is_opponent = self._creatures_are_opponents(creature_ref, target_ref)
        if disposition == "enemy" and not is_opponent:
            continue
        if disposition == "ally" and is_opponent:
            continue
        if disposition == "source" and target_ref != creature_ref:
            continue
        if (
            max_range is not None
            and grid_distance_between(
                creature_position,
                target_state.position,
            )
            > max_range
        ):
            continue
        target = self._spell_target_context(actor, target_ref)
        if target is not None:
            targets.append(target)
    return targets


def _spell_removal_choices(
    state: EncounterState,
    target_ref: str,
    spell: Spell,
) -> tuple[tuple[str, str], ...]:
    target = state._spell_target_context(
        state.creatures[state.current_decision().creature_ref].creature,
        target_ref,
    )
    if target is None:
        return ()
    choices: list[tuple[str, str]] = [
        (condition, condition.title())
        for condition in dict.fromkeys(target.target_conditions)
        if condition in capability_removable_conditions(spell.definition)
    ]
    if "curse" in capability_removable_effect_kinds(spell.definition):
        choices.extend(
            (
                f"curse@{effect.identity.id}",
                f"Curse: {effect.identity.source.label or effect.identity.source.definition_id}",
            )
            for effect in state.ongoing_effects
            if target_ref in effect.target_refs and effect.kind.value == "curse"
        )
    if "hit_point_maximum_reduction" in capability_removable_effect_kinds(
        spell.definition
    ) and any(
        target_ref in effect.target_refs
        and isinstance(
            maximum_modifier := effect.parameters.get("maximum_hit_point_modifier"),
            int,
        )
        and maximum_modifier < 0
        for effect in state.ongoing_effects
    ):
        choices.append(("hit_point_maximum_reduction", "Hit Point Maximum Reduction"))
    return tuple(choices)


def spell_area_targets(
    self: EncounterState,
    actor: Creature,
    spell: Spell,
    target_ref: str | None = None,
    aim_point: tuple[float, float] | None = None,
) -> tuple[CapabilityTargetContext, ...]:
    area = self._spell_area(actor, spell, target_ref=target_ref, aim_point=aim_point)
    if area is None:
        if target_ref is None:
            return ()
        target = self._spell_target_context(actor, target_ref)
        return (target,) if target is not None else ()
    return tuple(self._targets_in_area(actor, area))


def spend_spell_resources(
    self: EncounterState,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
    cast_level: int | None = None,
) -> None:
    if cost.action > 0:
        self._consume_action(allow_magic=True)
        self.active_attacks_remaining = 0
    if cost.bonus_action > 0:
        self.active_bonus_action_available = False
    if cost.reaction > 0:
        self.active_reaction_available = False
    if spell.level > 0:
        slot_level = cast_level if cast_level is not None else spell.level
        spellcasting.spell_slots_remaining[slot_level] -= 1


def spell_area(
    self: EncounterState,
    actor: Creature,
    spell: Spell,
    target_ref: str | None = None,
    aim_point: tuple[float, float] | None = None,
) -> AreaOfEffect | None:
    creature_ref = self.current_decision().creature_ref
    creature_position = self._creature_position(creature_ref)
    if capability_geometry_mode(spell.definition) == "point_area":
        if aim_point is None:
            return None
        radius_feet = capability_area_size_feet(spell.definition)
        if radius_feet is None:
            return None
        radius_squares = int(
            self.definition.grid.distance_from_feet(radius_feet, minimum=1)
        )
        origin = Position(int(aim_point[0]), int(aim_point[1]))
        if capability_area_shape(spell.definition) == "cube":
            return build_point_cube_area(origin, radius_squares, self.definition.grid)
        return build_radius_area(origin, radius_squares, self.definition.grid)
    if capability_geometry_mode(spell.definition) != "directional_area":
        return None
    if aim_point is not None:
        if (
            abs(aim_point[0] - (creature_position.x + 0.5)) < 1e-9
            and abs(aim_point[1] - (creature_position.y + 0.5)) < 1e-9
        ):
            return None
        direction = Vector2D(
            aim_point[0] - (creature_position.x + 0.5),
            aim_point[1] - (creature_position.y + 0.5),
        )
    else:
        if target_ref is None:
            return None
        target = self._spell_target_context(actor, target_ref)
        if target is None or target_ref == creature_ref:
            return None
        direction = vector_between_positions(
            creature_position,
            self._creature_position(target_ref),
        )
    length = self._spell_range_squares(spell, actor)
    if length is None:
        return None
    coverage_threshold = self.geometry_config.directional_area_cell_coverage_threshold
    return build_directional_area(
        spell.range_data.get("type"),
        creature_position,
        direction,
        length,
        self.definition.grid,
        coverage_threshold=coverage_threshold,
    )


def targets_in_area(
    self: EncounterState,
    actor: Creature,
    area: AreaOfEffect,
) -> list[CapabilityTargetContext]:
    occupied_cells = {(cell.x, cell.y) for cell in area.cells}
    targets: list[CapabilityTargetContext] = []
    for target_ref, target_state in self.creatures.items():
        if not target_state.is_alive:
            continue
        if (target_state.position.x, target_state.position.y) not in occupied_cells:
            continue
        target = self._spell_target_context(actor, target_ref)
        if target is not None:
            targets.append(target)
    return targets


def spell_target_context(
    self: EncounterState,
    actor: Creature,
    target_ref: str,
) -> CapabilityTargetContext | None:
    target_state = self.creatures.get(target_ref)
    if target_state is None or not target_state.is_alive:
        return None
    effective = self.effective_conditions_for(target_ref)
    return CapabilityTargetContext(
        creature=target_state.creature,
        target_ref=target_ref,
        target_label=target_state.creature.name,
        target_conditions=tuple(
            condition.condition.value for condition in self.conditions_for(target_ref)
        ),
        automatic_save_failures={
            "strength": effective.providers_for_trait(
                CombatTrait.AUTO_FAIL_STRENGTH_SAVES
            ),
            "dexterity": effective.providers_for_trait(
                CombatTrait.AUTO_FAIL_DEXTERITY_SAVES
            ),
        },
    )
