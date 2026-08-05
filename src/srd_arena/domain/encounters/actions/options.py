from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature, Spellcasting
from ...effects.conditions import CombatTrait
from ...geometry import (
    AreaOfEffect,
    Position,
    Vector2D,
    build_directional_area,
    build_radius_area,
    grid_distance_between,
    vector_between_positions,
)
from ..models import ActionCost, EncounterAction
from ...spells.definitions import Spell
from ...spells.resolution import SpellTargetContext
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
        if spell.geometry_mode in {"directional_area", "point_area"}:
            _append_spell_action_variants(actions, spellcasting, spell,
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
        for target in targets:
            selections = (
                tuple(
                    dict.fromkeys(
                        condition
                        for condition in target.target_conditions
                        if condition in spell.removable_conditions
                    )
                )
                if spell.removable_conditions
                else (None,)
            )
            for selection in selections:
                selection_label = (
                    f" ({selection.title()})"
                    if isinstance(selection, str)
                    else ""
                )
                selection_id = (
                    f"-{selection}" if isinstance(selection, str) else ""
                )
                _append_spell_action_variants(actions, spellcasting, spell,
                    EncounterAction(
                        spell_action_label(spell, actor_ref=creature_ref)
                        + selection_label,
                        "spell",
                        spell_action_value(
                            spell.id,
                            target.target_ref,
                            selected_condition=selection,
                        ),
                        id=spell_action_id(
                            spell,
                            target_ref=target.target_ref,
                        )
                        + selection_id,
                        creature_ref=creature_ref,
                        cost=cost,
                    ),
                )
        if not targets:
            _append_spell_action_variants(actions, spellcasting, spell,
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


def _append_spell_action_variants(
    actions: list[EncounterAction],
    spellcasting: Spellcasting,
    spell: Spell,
    action: EncounterAction,
) -> None:
    actions.append(action)
    if spell.level == 0 or spell.mechanics is None:
        return
    if spell.mechanics.slot_damage_increment is None:
        return
    spell_id, target_ref, aim_point = parse_spell_action_value(str(action.value))
    selected_condition = parse_spell_action_condition(str(action.value))
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
                    target_ref,
                    aim_point,
                    selected_condition,
                    slot_level,
                ),
                id=f"{action.id}-level-{slot_level}",
                creature_ref=action.creature_ref,
                cost=action.cost,
            )
        )


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
    return spell.geometry_mode == "self_only" or spell_targets_self_only(spell)


def spell_range_squares_for(
    self: EncounterState, spell: Spell, creature: Creature
) -> int | None:
    return spell_range_squares(spell, self.definition.grid)


def spell_action_targets(
    self: EncounterState,
    actor: Creature,
    spell: Spell,
) -> list[SpellTargetContext]:
    creature_ref = self.current_decision().creature_ref
    creature_position = self._creature_position(creature_ref)
    if spell.removable_conditions:
        restoration_targets: list[SpellTargetContext] = []
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
            if target is not None and any(
                condition in spell.removable_conditions
                for condition in target.target_conditions
            ):
                restoration_targets.append(target)
        return restoration_targets
    if spell.geometry_mode == "point_area":
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
        if any(
            condition in spell.removable_conditions
            for condition in target.target_conditions
        ):
            return [target]
        return []

    max_range = self._spell_range_squares(spell, actor)
    targets: list[SpellTargetContext] = []
    for target_ref, target_state in self.creatures.items():
        if not target_state.is_alive or not self._creatures_are_opponents(
            creature_ref,
            target_ref,
        ):
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


def spell_area_targets(
    self: EncounterState,
    actor: Creature,
    spell: Spell,
    target_ref: str | None = None,
    aim_point: tuple[float, float] | None = None,
) -> tuple[SpellTargetContext, ...]:
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
    if spell.geometry_mode == "point_area":
        if aim_point is None:
            return None
        radius_feet = spell.area_size_feet
        if radius_feet is None:
            return None
        radius_squares = int(
            self.definition.grid.distance_from_feet(radius_feet, minimum=1)
        )
        origin = Position(int(aim_point[0]), int(aim_point[1]))
        return build_radius_area(origin, radius_squares, self.definition.grid)
    if spell.geometry_mode != "directional_area":
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
) -> list[SpellTargetContext]:
    occupied_cells = {(cell.x, cell.y) for cell in area.cells}
    targets: list[SpellTargetContext] = []
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
) -> SpellTargetContext | None:
    target_state = self.creatures.get(target_ref)
    if target_state is None or not target_state.is_alive:
        return None
    effective = self.effective_conditions_for(target_ref)
    return SpellTargetContext(
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
