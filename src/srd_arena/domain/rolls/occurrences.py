"""Build stable addresses for D20 rolls within one action occurrence."""


def attack_roll_occurrence_id() -> str:
    """Return the address of a single ordinary attack roll."""

    return "attack-roll:1"


def spell_attack_occurrence_id(projectile_index: int) -> str:
    """Address one spell attack in its projectile order."""

    return f"spell-attack-roll:{projectile_index}"


def spell_save_occurrence_id(target_index: int) -> str:
    """Address one primary spell save in target order."""

    return f"spell-saving-throw:{target_index}"


def stat_block_save_occurrence_id(target_index: int) -> str:
    """Address one stat-block save in target order."""

    return f"stat-block-saving-throw:{target_index}"
