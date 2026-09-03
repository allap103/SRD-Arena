"""Expose the public creatures package API."""

from .attributes import Attributes, Movement
from .character_profiles import CharacterOptionRef, CharacterProfile
from .class_features import ClassFeature
from .classes import ClassRef
from .combat_profile import CombatProfile
from .equipment import Equipment
from .inventory import Inventory
from .model import Creature
from .multiattack import (
    Multiattack,
    MultiattackCount,
    MultiattackInvocation,
    MultiattackPlan,
    MultiattackReplacement,
    MultiattackRequirement,
    MultiattackStep,
)
from .resources import ResourceRecovery, RestType
from .size import can_grapple, is_two_sizes_smaller, normalize_size, size_rank
from .spellcasting import Spellcasting
from .stat_block_actions import (
    AttackActionDefinition,
    AutomaticActionDefinition,
    DeclaredStatBlockAction,
    SavingThrowActionDefinition,
    SpellcastingActionDefinition,
    SpellOption,
    StatBlockActionDefinition,
)
from .statistics import CreatureStatistics

__all__ = [
    "AttackActionDefinition",
    "Attributes",
    "AutomaticActionDefinition",
    "CharacterOptionRef",
    "CharacterProfile",
    "ClassFeature",
    "ClassRef",
    "CombatProfile",
    "Creature",
    "CreatureStatistics",
    "DeclaredStatBlockAction",
    "Equipment",
    "Inventory",
    "Movement",
    "Multiattack",
    "MultiattackCount",
    "MultiattackInvocation",
    "MultiattackPlan",
    "MultiattackReplacement",
    "MultiattackRequirement",
    "MultiattackStep",
    "ResourceRecovery",
    "RestType",
    "SavingThrowActionDefinition",
    "SpellOption",
    "Spellcasting",
    "SpellcastingActionDefinition",
    "StatBlockActionDefinition",
    "can_grapple",
    "is_two_sizes_smaller",
    "normalize_size",
    "size_rank",
]
