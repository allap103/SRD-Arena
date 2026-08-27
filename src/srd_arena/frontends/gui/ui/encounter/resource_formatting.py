"""Format turn resources and spell slots for compact GUI labels."""

from __future__ import annotations


def spell_slot_rich_text(level: int, remaining: int, maximum: int) -> str:
    """Render available and spent spell slots as colored square markers."""

    gap = "&nbsp;"
    available = gap.join(
        '<span style="color:#2f6f9d;">&#x25A0;</span>' for _ in range(remaining)
    )
    spent = gap.join(
        '<span style="color:#9d2f2f;">&#x25A0;</span>'
        for _ in range(max(0, maximum - remaining))
    )
    markers = gap.join(part for part in (available, spent) if part)
    return f"{level}: {markers}"
