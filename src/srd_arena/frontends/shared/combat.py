"""Provide combat support for the shared package."""

from srd_arena.application.api import EncounterObservation


def render_encounter_text(encounter: EncounterObservation) -> str:
    """Render a compact text alternative from the public encounter snapshot."""

    actor_ref = encounter.decision.creature_ref
    actor = encounter.creature(actor_ref)
    actor_position = actor.position
    rows: list[str] = []
    for y in range(encounter.grid.height):
        cells: list[str] = []
        for x in range(encounter.grid.width):
            if actor_position.x == x and actor_position.y == y:
                cells.append("A")
            else:
                cells.append(
                    "E"
                    if any(
                        creature.creature_ref != actor_ref
                        and creature.is_alive
                        and creature.position.x == x
                        and creature.position.y == y
                        for creature in encounter.creatures
                    )
                    else "."
                )
        rows.append(" ".join(cells))

    creatures = [
        f"- {creature.label}: {creature.health} HP "
        f"at ({creature.position.x}, {creature.position.y})"
        for creature in encounter.creatures
        if creature.creature_ref != actor_ref and creature.is_alive
    ] or ["- No other creatures remaining."]
    turn_label = actor.label
    if encounter.decision.kind == "reaction":
        turn_label = f"{turn_label} (Reaction)"
    return "\n".join(
        [
            *rows,
            "",
            f"Round {encounter.round_number} - Turn: {turn_label}",
            f"Movement remaining: {actor.movement_remaining}/{actor.movement_total} squares",
            f"Actor HP: {actor.health}/{actor.max_health} "
            f"at ({actor_position.x}, {actor_position.y})",
            f"Action available: {'yes' if actor.action_available else 'no'}",
            f"Attacks remaining in action: {actor.attacks_remaining}",
            f"Reaction available: {'yes' if actor.reaction_available else 'no'}",
            "Other creatures:",
            *creatures,
        ]
    )
