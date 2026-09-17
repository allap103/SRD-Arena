"""Bounded local preparation choices; no draft edit is an engine command."""

from dataclasses import replace

from srd_arena.engine.api import CastSpell

from .actions import Candidate


def preparation_choices(draft: Candidate, *, maximum: int) -> tuple[Candidate, ...]:
    """Offer monotonic target additions or completion, avoiding joint enumeration."""
    options = draft.cast_options
    assert options is not None and isinstance(draft.command, CastSpell)
    result: list[Candidate] = []
    if options.resource_pool is not None:
        if draft.allocations:
            result.append(replace(draft, cast_complete=True))
        used = dict(draft.allocations)
        remaining = options.resource_pool - sum(used.values())
        for ref, limit in options.resource_limits:
            if ref in used:
                continue
            for amount in range(1, min(limit, remaining) + 1):
                refs = (*draft.selected_refs, ref)
                allocations = (*draft.allocations, (ref, amount))
                result.append(
                    replace(
                        draft,
                        selected_refs=refs,
                        allocations=allocations,
                        target_ref=ref,
                        amount=amount,
                        command=replace(
                            draft.command, target_refs=refs, allocations=allocations
                        ),
                        cast_complete=amount == remaining
                        or len(allocations) == len(options.resource_limits),
                    )
                )
                if len(result) > maximum:
                    raise ValueError("Spell preparation exceeds candidate capacity")
    else:
        count = len(draft.selected_refs)
        if count and (
            not options.require_full_count or count == options.maximum_targets
        ):
            result.append(replace(draft, cast_complete=True))
        if count < options.maximum_targets:
            for ref in options.target_refs:
                if not options.repeat_targets and ref in draft.selected_refs:
                    continue
                refs = (*draft.selected_refs, ref)
                result.append(
                    replace(
                        draft,
                        selected_refs=refs,
                        target_ref=ref,
                        command=replace(draft.command, target_refs=refs),
                        cast_complete=len(refs) == options.maximum_targets,
                    )
                )
                if len(result) > maximum:
                    raise ValueError("Spell preparation exceeds candidate capacity")
    if not result:
        # Preserve the attempt when public information offers no selection.
        # The engine rejects invalid empty/incomplete input without spending.
        return (replace(draft, cast_complete=True),)
    return tuple(result)
