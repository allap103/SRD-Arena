"""Expose the public creatures package API."""

from .appearance import (
    ApparentArmorCategory,
    ApparentFocusKind,
    ObservableAppearance,
)
from .armor_class import ArmorClassCalculation
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
from .rule_providers import IntrinsicRuleProvider
from .size import (
    can_grapple,
    footprint_width,
    is_two_sizes_smaller,
    normalize_size,
    size_rank,
)
from .spellcasting import Spellcasting
from .stat_block_actions import (
    AttackActionDefinition,
    AutomaticActionDefinition,
    DeclaredStatBlockAction,
    ParryReactionDefinition,
    SavingThrowActionDefinition,
    SpellcastingActionDefinition,
    SpellOption,
    StandardActionGrantDefinition,
    StatBlockActionDefinition,
)
from .statistics import CreatureStatistics

__all__ = [
    "ApparentArmorCategory",
    "ApparentFocusKind",
    "ArmorClassCalculation",
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
    "IntrinsicRuleProvider",
    "Inventory",
    "Movement",
    "Multiattack",
    "MultiattackCount",
    "MultiattackInvocation",
    "MultiattackPlan",
    "MultiattackReplacement",
    "MultiattackRequirement",
    "MultiattackStep",
    "ObservableAppearance",
    "ParryReactionDefinition",
    "ResourceRecovery",
    "RestType",
    "SavingThrowActionDefinition",
    "SpellOption",
    "Spellcasting",
    "SpellcastingActionDefinition",
    "StandardActionGrantDefinition",
    "StatBlockActionDefinition",
    "can_grapple",
    "footprint_width",
    "is_two_sizes_smaller",
    "normalize_size",
    "size_rank",
]
