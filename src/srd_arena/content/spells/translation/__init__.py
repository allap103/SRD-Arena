"""Concern-based compilation of authored spell content."""

from .activation import compile_activation
from .capabilities import compile_definition

__all__ = ["compile_activation", "compile_definition"]
