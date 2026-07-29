from ...domain.creatures import Creature
from ...domain.encounters.behaviors import movement_squares
from ...domain.encounters.encounter import EncounterState


def render_encounter_text(encounter: EncounterState, player: Creature) -> str:
    rows: list[str] = []
    for y in range(encounter.definition.grid.height):
        cells: list[str] = []
        for x in range(encounter.definition.grid.width):
            if encounter.primary_position.x == x and encounter.primary_position.y == y:
                cells.append("P")
            else:
                cells.append(
                    "E"
                    if encounter.living_non_primary_creature_at(x, y)
                    else "."
                )
        rows.append(" ".join(cells))

    creatures = [
        f"- {encounter._creature_label(creature_ref)}: "
        f"{creature_state.creature.get_health()} HP "
        f"at ({creature_state.position.x}, {creature_state.position.y})"
        for creature_ref, creature_state in encounter.creatures.items()
        if creature_ref != encounter.primary_creature_ref
        and creature_state.is_alive
    ] or ["- No other creatures remaining."]
    movement = encounter.active_movement_remaining_for(player)
    return "\n".join(
        [
            *rows,
            "",
            f"Round {encounter.round_number} - Turn: {encounter.current_turn_label()}",
            f"Movement remaining: {movement}/{movement_squares(player)} squares",
            f"Player HP: {player.get_health()}/{player.get_max_health()} "
            f"at ({encounter.primary_position.x}, {encounter.primary_position.y})",
            f"Actions remaining: {encounter.active_actions_remaining}",
            f"Attacks remaining in action: {encounter.active_attacks_remaining}",
            f"Reaction available: {'yes' if encounter.active_reaction_available else 'no'}",
            "Other creatures:",
            *creatures,
        ]
    )
