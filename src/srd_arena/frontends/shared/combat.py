from ...domain.creatures import Creature
from ...domain.combat.behaviors import movement_squares
from ...domain.combat.encounter import EncounterState


def render_encounter_text(encounter: EncounterState, player: Creature) -> str:
    rows: list[str] = []
    for y in range(encounter.definition.grid.height):
        cells: list[str] = []
        for x in range(encounter.definition.grid.width):
            if encounter.player_position.x == x and encounter.player_position.y == y:
                cells.append("P")
            else:
                cells.append("E" if encounter.living_enemy_at(x, y) else ".")
        rows.append(" ".join(cells))

    enemies = [
        f"- Enemy {index + 1} ({enemy.creature.name}): {enemy.creature.get_health()} HP "
        f"at ({enemy.position.x}, {enemy.position.y})"
        for index, enemy in enumerate(encounter.enemies)
        if enemy.is_alive
    ] or ["- No enemies remaining."]
    movement = encounter.player_movement_remaining_for(player)
    return "\n".join(
        [
            *rows,
            "",
            f"Round {encounter.round_number} - Turn: {encounter.current_turn_label()}",
            f"Movement remaining: {movement}/{movement_squares(player)} squares",
            f"Player HP: {player.get_health()}/{player.get_max_health()} "
            f"at ({encounter.player_position.x}, {encounter.player_position.y})",
            f"Actions remaining: {encounter.player_actions_remaining}",
            f"Attacks remaining in action: {encounter.player_attacks_remaining}",
            f"Reaction available: {'yes' if encounter.player_reaction_available else 'no'}",
            "Enemies:",
            *enemies,
        ]
    )
