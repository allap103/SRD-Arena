from dataclasses import FrozenInstanceError

import pytest

from srd_arena.domain.creatures import Equipment


def test_authored_hand_loadout_cannot_change_during_an_encounter() -> None:
    equipment = Equipment(right_hand="greatsword")

    with pytest.raises(FrozenInstanceError):
        equipment.right_hand = "longsword"  # type: ignore[misc]
