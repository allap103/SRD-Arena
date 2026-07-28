from srd_arena.content.schemas.multiattack import (
    CastSpellInvocationSchema,
    ChoiceStepSchema,
    CreatureStatCountSchema,
    HalfSpellLevelCountSchema,
    MultiattackInvocationSchema,
    MultiattackMechanicsSchema,
    StatBlockActionInvocationSchema,
)
from srd_arena.domain.creatures import (
    Multiattack,
    MultiattackCount,
    MultiattackInvocation,
    MultiattackPlan,
    MultiattackReplacement,
    MultiattackRequirement,
    MultiattackStep,
)


def build_multiattack(
    mechanics: MultiattackMechanicsSchema | None,
) -> Multiattack | None:
    if mechanics is None:
        return None
    return Multiattack(
        plans=tuple(
            MultiattackPlan(
                steps=tuple(
                    MultiattackStep(
                        options=tuple(
                            _build_invocation(invocation)
                            for invocation in (
                                step.options
                                if isinstance(step, ChoiceStepSchema)
                                else (step.invocation,)
                            )
                        ),
                        times=_build_count(step.times),
                        availability=step.availability,
                    )
                    for step in plan.steps
                ),
                ordering=plan.ordering,
                replacements=tuple(
                    MultiattackReplacement(
                        target_kind=replacement.target.type,
                        target_name=getattr(replacement.target, "name", None),
                        target_step=getattr(replacement.target, "index", None),
                        options=tuple(
                            _build_invocation(option)
                            for option in replacement.options
                        ),
                        replace_count=replacement.replace_count,
                        maximum_uses=replacement.maximum_uses,
                        requirement=_build_requirement(
                            replacement.requirement
                        ),
                    )
                    for replacement in plan.replacements
                ),
                requirement=_build_requirement(plan.requirement),
            )
            for plan in mechanics.plans
        )
    )


def _build_count(
    count: int | CreatureStatCountSchema | HalfSpellLevelCountSchema,
) -> int | MultiattackCount:
    if isinstance(count, int):
        return count
    if isinstance(count, CreatureStatCountSchema):
        return MultiattackCount(kind="creature_stat", stat=count.stat)
    return MultiattackCount(kind="half_spell_level", rounding=count.round)


def _build_requirement(requirement) -> MultiattackRequirement | None:
    if requirement is None:
        return None
    return MultiattackRequirement(
        kind="action_used_this_turn",
        action=requirement.action,
    )


def _build_invocation(
    invocation: MultiattackInvocationSchema,
) -> MultiattackInvocation:
    if isinstance(invocation, StatBlockActionInvocationSchema):
        return MultiattackInvocation(
            kind="stat_block_action",
            name=invocation.name,
            section=invocation.section,
        )
    assert isinstance(invocation, CastSpellInvocationSchema)
    return MultiattackInvocation(
        kind="cast_spell",
        name=invocation.spell.name,
        section=invocation.via_section,
        source=invocation.spell.source,
        cast_level=invocation.cast_level,
    )
