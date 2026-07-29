from ...domain.encounters.behaviors import movement_squares
from ...domain.encounters.encounter import EncounterState


def render_encounter_text(encounter: EncounterState) -> str:
    actor_ref = encounter.current_decision().creature_ref
    actor = encounter.active_creature_state.creature
    actor_position = encounter.active_position
    rows: list[str] = []
    for y in range(encounter.definition.grid.height):
        cells: list[str] = []
        for x in range(encounter.definition.grid.width):
            if actor_position.x == x and actor_position.y == y:
                cells.append("A")
            else:
                cells.append(
                    "E"
                    if any(
                        creature_ref != actor_ref
                        and creature_state.is_alive
                        and creature_state.position.x == x
                        and creature_state.position.y == y
                        for creature_ref, creature_state in encounter.creatures.items()
                    )
                    else "."
                )
        rows.append(" ".join(cells))

    creatures = [
        f"- {encounter._creature_label(creature_ref)}: "
        f"{creature_state.creature.get_health()} HP "
        f"at ({creature_state.position.x}, {creature_state.position.y})"
        for creature_ref, creature_state in encounter.creatures.items()
        if creature_ref != actor_ref
        and creature_state.is_alive
    ] or ["- No other creatures remaining."]
    movement = encounter._active_movement_remaining()
    return "\n".join(
        [
            *rows,
            "",
            f"Round {encounter.round_number} - Turn: {encounter.current_turn_label()}",
            f"Movement remaining: {movement}/{movement_squares(actor)} squares",
            f"Actor HP: {actor.get_health()}/{actor.get_max_health()} "
            f"at ({actor_position.x}, {actor_position.y})",
            f"Actions remaining: {encounter.active_actions_remaining}",
            f"Attacks remaining in action: {encounter.active_attacks_remaining}",
            f"Reaction available: {'yes' if encounter.active_reaction_available else 'no'}",
            "Other creatures:",
            *creatures,
        ]
    )
