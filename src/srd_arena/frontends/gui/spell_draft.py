"""Local spell selection edits; only a completed draft becomes an engine command."""

from dataclasses import dataclass, field, replace

from srd_arena.engine.api import (
    ActionObservation,
    CastSpell,
    GameObservation,
    GameUpdate,
    TargetingObservation,
    TargetResourceAllocationObservation,
    TargetResourceLimitObservation,
)


@dataclass
class SpellDraft:
    """Own an editable selection bound to the engine decision it was opened from."""

    base: GameObservation
    action: ActionObservation
    aim: tuple[float, float] | None
    targets: list[str] = field(default_factory=list)
    allocations: dict[str, int] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        """Whether the local configuration has enough input to submit."""
        options = self.action.spell_cast
        assert options is not None
        if options.resource_pool is not None:
            return bool(self.allocations)
        return bool(self.targets) and (
            not options.require_full_count
            or len(self.targets) == options.maximum_targets
        )

    def change_target(self, ref: str, remove: bool) -> None:
        """Change one local target allocation without touching the session."""
        options = self.action.spell_cast
        assert options is not None
        if remove:
            if ref not in self.targets:
                raise ValueError("Target has no allocation to remove.")
            self.targets.remove(ref)
        elif ref not in options.target_refs:
            raise ValueError("Target is not advertised.")
        elif len(self.targets) >= options.maximum_targets:
            raise ValueError("Target limit reached.")
        elif options.repeat_targets or ref not in self.targets:
            self.targets.append(ref)

    def allocate(self, ref: str, amount: int) -> None:
        """Assign a local whole-number share of a shared resource pool."""
        options = self.action.spell_cast
        assert options is not None
        if (
            options.resource_pool is None
            or type(amount) is not int
            or amount < 0
            or amount > dict(options.resource_limits).get(ref, -1)
            or sum(v for r, v in self.allocations.items() if r != ref) + amount
            > options.resource_pool
        ):
            raise ValueError("Invalid resource allocation.")
        if amount:
            self.allocations[ref] = amount
        else:
            self.allocations.pop(ref, None)

    def command(self) -> CastSpell:
        """Freeze a complete cast for validation at the original decision."""
        assert self.base.encounter is not None
        if not self.ready:
            raise ValueError("Complete the spell selection before casting.")
        return CastSpell(
            self.action.id,
            self.base.encounter.decision.id,
            tuple(self.allocations) if self.allocations else tuple(self.targets),
            tuple(self.allocations.items()),
            self.aim,
        )

    def update(self) -> GameUpdate:
        """Overlay the GUI's local draft on the unchanged engine observation."""
        options = self.action.spell_cast
        encounter = self.base.encounter
        assert options is not None and encounter is not None
        labels = {c.creature_ref: c.name for c in encounter.creatures}
        actions = []
        actor = self.action.creature_ref

        def add(ref: str | None, label: str, kind: str, suffix: str = "") -> None:
            actions.append(
                ActionObservation(
                    id=f"draft-{ref or kind}{suffix}",
                    label=label,
                    kind=kind,
                    creature_ref=actor,
                    target_ref=ref,
                    source_trigger_id=self.action.source_id,
                )
            )

        if options.resource_pool is not None:
            for ref, _limit in options.resource_limits:
                add(
                    ref,
                    f"Allocate healing to {labels.get(ref, ref)}",
                    "set_spell_resource_allocation",
                )
        else:
            for ref in options.target_refs:
                count = self.targets.count(ref)
                if count:
                    add(
                        ref,
                        f"Remove {labels.get(ref, ref)} ({count})",
                        "toggle_spell_target",
                        "-remove",
                    )
                if len(self.targets) < options.maximum_targets and (
                    options.repeat_targets or not count
                ):
                    add(
                        ref,
                        f"Add {labels.get(ref, ref)}",
                        "toggle_spell_target",
                        "-add",
                    )
        if self.ready:
            add(
                None,
                f"Cast {self.action.source_label or self.action.label}",
                "confirm_spell_targets",
            )
        add(None, "Cancel spell", "cancel_spell_targets")
        targeting = TargetingObservation(
            self.action.source_id or "",
            self.action.source_label or self.action.label,
            tuple(self.targets),
            options.maximum_targets,
            options.repeat_targets,
            options.require_full_count,
            options.resource_pool,
            tuple(
                TargetResourceAllocationObservation(r, n)
                for r, n in self.allocations.items()
            ),
            tuple(
                TargetResourceLimitObservation(r, n) for r, n in options.resource_limits
            ),
        )
        view = replace(
            self.base,
            scene=replace(self.base.scene, action_details=tuple(actions)),
            encounter=replace(
                encounter,
                targeting=targeting,
                decision=replace(encounter.decision, kind="spell_targets"),
            ),
        )
        return GameUpdate(view, (), (), None, None, False)
