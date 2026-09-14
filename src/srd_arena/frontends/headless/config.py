"""Bounded YAML input with strict grammar and implementation support checks."""

import hashlib
from pathlib import Path

import yaml
from yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
    NodeEvent,
    ScalarEvent,
)
from yaml.nodes import MappingNode

from srd_arena.engine.api import ObservationPolicy
from srd_arena.frontends.headless.serialization import canonical_json

MAX_POLICY_BYTES = 65536
MAX_POLICY_DEPTH = 16


class PolicyConfigError(ValueError):
    """Invalid syntax, invalid grammar, or unsupported observation policy."""


class _UniqueSafeLoader(yaml.SafeLoader):
    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[object, object]:
        result: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise PolicyConfigError("Policy mapping keys must be strings")
            if key in result:
                raise PolicyConfigError(
                    f"Duplicate key {key!r} at line {key_node.start_mark.line + 1}"
                )
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def load_policy(path: Path) -> ObservationPolicy:
    """Read a complete policy and reject unsupported requests before launch."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_POLICY_BYTES + 1)
        if len(raw) > MAX_POLICY_BYTES:
            raise PolicyConfigError(f"Policy exceeds {MAX_POLICY_BYTES} bytes")
        source = raw.decode("utf-8")
        depth = 0
        for event in yaml.parse(source, Loader=yaml.SafeLoader):
            if isinstance(event, AliasEvent) or (
                isinstance(event, NodeEvent) and event.anchor is not None
            ):
                raise PolicyConfigError("YAML anchors and aliases are not supported")
            if (
                isinstance(event, (ScalarEvent, CollectionStartEvent))
                and event.tag is not None
            ):
                raise PolicyConfigError("Explicit YAML tags are not supported")
            if isinstance(event, CollectionStartEvent):
                depth += 1
                if depth > MAX_POLICY_DEPTH:
                    raise PolicyConfigError(
                        f"Policy exceeds nesting depth {MAX_POLICY_DEPTH}"
                    )
            elif isinstance(event, CollectionEndEvent):
                depth -= 1
        value = yaml.load(source, Loader=_UniqueSafeLoader)
        policy = ObservationPolicy.model_validate_json(
            canonical_json(value), strict=True
        )
        policy.validate_support()
        return policy
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, TypeError) as exc:
        raise PolicyConfigError(f"{path}: {exc}") from exc


def policy_digest(policy: ObservationPolicy) -> str:
    """Identify resolved settings independently of YAML comments/key order."""
    return hashlib.sha256(canonical_json(policy).encode("utf-8")).hexdigest()
