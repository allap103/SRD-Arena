"""Schemas and catalogs for authored class content."""

from .catalog import (
    ClassCatalog,
    ClassRecord,
    SubclassCatalog,
    SubclassRecord,
    load_class_catalog,
    load_subclass_catalog,
)
from .optional_feature_catalog import (
    OptionalFeatureCatalog,
    load_optional_feature_catalog,
)
from .optional_feature_effects import normalize_optional_feature_effects
from .optional_feature_schema import OptionalFeatureSchema
from .schema import (
    ClassFeatureReferenceSchema,
    ClassFeatureSchema,
    ClassSchema,
    ClassTableGroupSchema,
    StartingProficienciesSchema,
    SubclassFeatureSchema,
    SubclassSchema,
)

__all__ = [
    "ClassCatalog",
    "ClassFeatureReferenceSchema",
    "ClassFeatureSchema",
    "ClassRecord",
    "ClassSchema",
    "ClassTableGroupSchema",
    "OptionalFeatureCatalog",
    "OptionalFeatureSchema",
    "StartingProficienciesSchema",
    "SubclassCatalog",
    "SubclassFeatureSchema",
    "SubclassRecord",
    "SubclassSchema",
    "load_class_catalog",
    "load_optional_feature_catalog",
    "load_subclass_catalog",
    "normalize_optional_feature_effects",
]
