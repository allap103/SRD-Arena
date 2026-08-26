"""Extract display-ready condition names from serialized creature state."""

from typing import Any


def effective_condition_names(creature: dict[str, Any]) -> tuple[str, ...]:
    """Return deduplicated effective conditions, falling back to raw state."""

    effective = creature.get("effective_conditions")
    if isinstance(effective, list):
        return tuple(
            dict.fromkeys(
                condition["condition"]
                for condition in effective
                if isinstance(condition, dict)
                and isinstance(condition.get("condition"), str)
            )
        )
    return tuple(
        dict.fromkeys(
            condition
            for condition in creature.get("conditions", [])
            if isinstance(condition, str)
        )
    )
