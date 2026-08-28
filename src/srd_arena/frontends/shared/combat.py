"""Project application combat observations into frontend presentation models."""

from srd_arena.application.api import EncounterObservation


def render_encounter_text(encounter: EncounterObservation) -> str:
    """Render a compact text alternative from the public encounter snapshot.

    >>> from types import SimpleNamespace
    >>> hero = SimpleNamespace(
    ...     creature_ref="hero", label="Hero", position=SimpleNamespace(x=0, y=0),
    ...     health=10, max_health=12, is_alive=True, movement_remaining=5,
    ...     movement_total=6, action_available=True, attacks_remaining=0,
    ...     reaction_available=True,
    ... )
    >>> encounter = SimpleNamespace(
    ...     decision=SimpleNamespace(creature_ref="hero", kind="turn"),
    ...     creature=lambda ref: hero, creatures=(hero,), round_number=1,
    ...     grid=SimpleNamespace(width=2, height=1),
    ... )
    >>> print(render_encounter_text(encounter).splitlines()[0])
    A .
    """

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
