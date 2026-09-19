"""Parse the simple dice expressions shared by combat rule pipelines."""

import re


def parse_dice_expression(expression: str) -> tuple[int, int]:
    """Return the count and die size from a simple ``NdS`` expression.

    >>> parse_dice_expression("8d6")
    (8, 6)
    >>> parse_dice_expression("2D10")
    (2, 10)
    >>> parse_dice_expression("d6")
    Traceback (most recent call last):
    ...
    ValueError: Unsupported dice expression: 'd6'
    """

    match = re.fullmatch(r"(\d+)[dD](\d+)", expression)
    if match is None:
        raise ValueError(f"Unsupported dice expression: {expression!r}")
    return int(match.group(1)), int(match.group(2))
