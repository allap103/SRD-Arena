from dataclasses import dataclass


@dataclass
class Position:
    x: int
    y: int


@dataclass
class Grid:
    width: int
    height: int
