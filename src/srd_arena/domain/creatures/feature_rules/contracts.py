"""Feature-specific callable contracts shared by Python rule handlers."""

from collections.abc import Callable

HealingReceiver = Callable[[int], int]
