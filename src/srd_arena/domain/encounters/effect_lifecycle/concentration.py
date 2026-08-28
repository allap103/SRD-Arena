"""Own concentration replacement, damage saves, and termination."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ...effects.runtime import OngoingEffectKind
from ...rolls.saving_throws import SavingThrowCreature, resolve_saving_throw
from .removal import _remove_effect_tree

if TYPE_CHECKING:
    from ..encounter import EncounterState
    from ..encounter_models.resolution import EncounterProgress


def end_concentration(state: EncounterState, source_ref: str) -> None:
    """End every concentration effect maintained by one creature.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> source = SimpleNamespace(applied_by_ref="mage")
    >>> effect = SimpleNamespace(
    ...     kind=OngoingEffectKind.CONCENTRATION,
    ...     identity=SimpleNamespace(source=source),
    ... )
    >>> state = SimpleNamespace(ongoing_effects=[effect])
    >>> with patch(
    ...     "srd_arena.domain.encounters.effect_lifecycle.concentration."
    ...     "_remove_effect_tree"
    ... ) as remove:
    ...     end_concentration(state, "mage")
    >>> remove.call_args.args[1] is effect
    True
    """

    matching = tuple(
        effect
        for effect in state.ongoing_effects
        if effect.kind is OngoingEffectKind.CONCENTRATION
        and effect.identity.source.applied_by_ref == source_ref
    )
    for effect in matching:
        _remove_effect_tree(state, effect)


def resolve_concentration_damage(
    state: EncounterState,
    creature_ref: str,
    damage: int,
    progress: EncounterProgress | None = None,
) -> None:
    """Resolve the concentration save caused by one damage application.

    A defeated creature loses concentration immediately without rolling.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import Mock, patch
    >>> source = SimpleNamespace(applied_by_ref="mage")
    >>> effect = SimpleNamespace(
    ...     kind=OngoingEffectKind.CONCENTRATION,
    ...     identity=SimpleNamespace(source=source),
    ... )
    >>> creature = SimpleNamespace(get_health=lambda: 0)
    >>> state = SimpleNamespace(
    ...     ongoing_effects=[effect],
    ...     creatures={"mage": SimpleNamespace(creature=creature)},
    ... )
    >>> with patch(
    ...     "srd_arena.domain.encounters.effect_lifecycle.concentration."
    ...     "end_concentration"
    ... ) as end:
    ...     resolve_concentration_damage(state, "mage", 8)
    >>> end.call_args.args[1]
    'mage'
    """

    if damage <= 0:
        return
    concentrating = next(
        (
            effect
            for effect in state.ongoing_effects
            if effect.kind is OngoingEffectKind.CONCENTRATION
            and effect.identity.source.applied_by_ref == creature_ref
        ),
        None,
    )
    if concentrating is None:
        return
    creature = state.creatures[creature_ref].creature
    if creature.get_health() <= 0:
        end_concentration(state, creature_ref)
        return
    dc = max(10, damage // 2)
    roll_rules = state.combat_rules.roll_modifiers(
        state,
        creature_ref,
        "saving_throw",
        ability="constitution",
    )
    save = resolve_saving_throw(
        cast(SavingThrowCreature, creature),
        "constitution",
        dc,
        sourced_modifier_override=roll_rules.resolve_modifier(state.dice.roll_die),
        sourced_mode_override=roll_rules.mode,
        roller=state.dice.roll_die,
    )
    if progress is not None:
        outcome = "maintains" if save.check.success else "loses"
        effect_label = (
            concentrating.label
            or concentrating.identity.source.definition_id.replace("_", " ").title()
        )
        progress.messages.append(
            (
                "system",
                f"{creature.name} {outcome} concentration on {effect_label} "
                f"(Constitution {save.check.roll.total} vs DC {dc}).",
            )
        )
    if not save.check.success:
        end_concentration(state, creature_ref)
