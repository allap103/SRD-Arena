from srd_arena.content.schemas.action_mechanics import (
    ActionEffectSchema,
    ActionTargetSchema,
    AttackActionMechanicsSchema,
    SavingThrowActionMechanicsSchema,
)
from srd_arena.content.schemas.bestiary import BestiaryMonsterSchema
from srd_arena.domain.creatures.stat_block_actions import (
    ActionEffect,
    ActionOutcomeStage,
    ActionTarget,
    AttackActionDefinition,
    SavingThrowActionDefinition,
    StatBlockActionDefinition,
)


def build_stat_block_actions(
    stat_block: BestiaryMonsterSchema | None,
) -> dict[str, StatBlockActionDefinition]:
    if stat_block is None:
        return {}
    definitions: dict[str, StatBlockActionDefinition] = {}
    for action in stat_block.action:
        mechanics = action.mechanics
        if isinstance(mechanics, AttackActionMechanicsSchema):
            definitions[action.name] = AttackActionDefinition(
                name=action.name,
                attack_modes=tuple(mechanics.attack_modes),
                attack_bonus=mechanics.attack_bonus,
                target=_build_target(mechanics.target),
                reach_feet=mechanics.reach_feet,
                range_normal_feet=mechanics.range_normal_feet,
                range_long_feet=mechanics.range_long_feet,
                hit=tuple(_build_effect(effect) for effect in mechanics.hit),
            )
        elif isinstance(mechanics, SavingThrowActionMechanicsSchema):
            definitions[action.name] = SavingThrowActionDefinition(
                name=action.name,
                target=_build_target(mechanics.target),
                ability=mechanics.ability,
                dc=mechanics.dc,
                failure=tuple(
                    ActionOutcomeStage(
                        effects=tuple(
                            _build_effect(effect) for effect in stage.effects
                        ),
                        repeat_saves=tuple(
                            repeat.model_dump(exclude_none=True)
                            for repeat in stage.repeat_saves
                        ),
                    )
                    for stage in mechanics.failure
                ),
                success=tuple(
                    _build_effect(effect) for effect in mechanics.success
                ),
                success_damage=mechanics.success_damage,
                always=tuple(
                    _build_effect(effect) for effect in mechanics.always
                ),
                resource=(
                    mechanics.resource.model_dump(exclude_none=True)
                    if mechanics.resource is not None
                    else None
                ),
            )
    return definitions


def _build_target(target: ActionTargetSchema) -> ActionTarget:
    data = target.model_dump(exclude_none=True)
    return ActionTarget(
        kind=target.type,
        range_feet=data.get("range_feet"),
        shape=data.get("shape"),
        size_feet=data.get("size_feet"),
        width_feet=data.get("width_feet"),
        line_of_sight=bool(data.get("line_of_sight", False)),
        requirements=tuple(data.get("requirements", [])),
    )


def _build_effect(effect: ActionEffectSchema) -> ActionEffect:
    data = effect.model_dump(exclude={"type"}, exclude_none=True)
    return ActionEffect(kind=effect.type, parameters=data)
