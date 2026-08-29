"""Shared scenario setup and action helpers for encounter integration tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from srd_arena.content.spells import SpellCatalog, build_spell
from srd_arena.domain.creatures import Creature
from srd_arena.domain.encounters import EncounterOrchestrator
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.participants import creature_controller
from srd_arena.domain.rolls.dice import DieRoller
from srd_arena.domain.rolls.randomness import DiceRoller
from srd_arena.domain.spells import Spell
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.queries import ActionAim, DirectTargetOptionDetails
from srd_arena.engine.session import Session

ORCHESTRATOR = EncounterOrchestrator()

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
TACTICAL_SCENARIO_DIR = Path(__file__).parent / "fixtures" / "tactical_game"
MULTIATTACK_SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "multiattack_showcase"
)
STAT_BLOCK_ACTION_SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "stat_block_action_showcase"
)
CONDITIONS_SHOWCASE_SCENARIO_DIR = (
    Path(__file__).parents[1] / "content" / "scenarios" / "conditions_showcase"
)
ROLL_INITIATIVE = EncounterState.roll_initiative


def as_mapping(value: object) -> Mapping[str, object]:
    """Narrow an event payload to a mapping after asserting its runtime shape."""

    assert isinstance(value, Mapping)
    return cast(Mapping[str, object], value)


def as_sequence(value: object) -> Sequence[object]:
    """Narrow an event payload to a sequence after asserting its runtime shape."""

    assert isinstance(value, Sequence)
    return cast(Sequence[object], value)


def build_referenced_spell(
    name: str,
    source: str | None,
    catalog: SpellCatalog,
) -> Spell:
    """Build one runtime spell selected from a loaded catalog."""

    return build_spell(catalog.find(name, source))


@pytest.fixture(autouse=True)
def player_first_initiative(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep external actors first unless a test restores real initiative rolls."""

    def fixed_initiative(self: EncounterState) -> None:
        self.initiative_entries = []
        first_external_ref = next(
            creature_ref
            for creature_ref in self.creatures
            if creature_controller(self, creature_ref) == "external"
        )
        self.initiative_order = [
            first_external_ref,
            *(
                creature_ref
                for creature_ref in self.creatures
                if creature_ref != first_external_ref
            ),
        ]

    monkeypatch.setattr(EncounterState, "roll_initiative", fixed_initiative)


def action_id_by_label(session: Session, label: str) -> str:
    """Return the unique advertised action whose label matches exactly."""

    return next(
        action.id for action in session.read().action_options if action.label == label
    )


def action_labels(session: Session) -> list[str]:
    """Return the labels of all actions in the session's current decision."""

    return [action.label for action in session.read().action_options]


def action_id_by_prefix(session: Session, prefix: str) -> str:
    """Return the first advertised action whose label starts with the prefix."""

    return next(
        action.id
        for action in session.read().action_options
        if action.label.startswith(prefix)
    )


def action_id(session: Session, kind: str, value: object) -> str:
    """Return a direct-target action matching its kind and target reference."""

    return next(
        action.id
        for action in session.read().action_options
        if action.kind == kind
        and isinstance(action.details, DirectTargetOptionDetails)
        and action.details.target_ref == value
    )


def active_creature(session: Session) -> Creature:
    """Return the active creature from a concrete integration-test session."""

    if session.encounter_state is None:
        session.read()
    state = session.encounter_state
    assert state is not None
    return state.active_creature_state.creature


def choose_advertised_action(
    session: Session,
    action: EncounterAction,
) -> EngineOutcome:
    """Submit a domain action through the engine's advertised-ID boundary."""

    advertised_ids = {option.id for option in session.read().action_options}
    assert action.id in advertised_ids
    return session.choose(action.id)


def use_deterministic_dice(
    session: Session,
    *,
    die_roller: DieRoller | None = None,
) -> DiceRoller:
    """Inject one deterministic individual-die source through composition."""

    current = session._dice
    configured = DiceRoller(
        die_roller=die_roller or current.die_roller,
    )
    session._dice = configured
    if session.encounter_state is not None:
        session.encounter_state.dice = configured
    return configured


def choose_directional_spell(
    session: Session,
    label: str,
    aim_cell: tuple[int, int],
) -> EngineOutcome:
    """Configure a directional spell by aiming at a grid-cell center."""

    scene_view = session.read()
    action = next(
        detail for detail in scene_view.action_options if detail.label == label
    )
    return session.configure_action(
        action.id,
        ActionAim(x=aim_cell[0] + 0.5, y=aim_cell[1] + 0.5),
    )
