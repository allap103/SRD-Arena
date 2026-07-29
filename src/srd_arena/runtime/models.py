from dataclasses import dataclass, field

from srd_arena.domain.encounters.models import CombatEvent


@dataclass
class SceneView:
    """Runtime snapshot of the current scene and its selectable actions."""

    scene_id: str
    scene_text: str | None
    action_details: list["ActionView"] = field(default_factory=list)


@dataclass
class ActionView:
    """Runtime description of an action available to a caller."""

    id: str
    label: str
    kind: str
    creature_ref: str
    value: str | int | None = None
    cost: dict[str, int] = field(default_factory=dict)
    enabled: bool = True
    unavailable_reason: str | None = None
    source_trigger_id: str | None = None
    preferred_attack_type: str | None = None
    preferred_attack_name: str | None = None


@dataclass
class TurnResult:
    """Outcome of applying one selected action or choice."""

    scene: SceneView
    selected_choice_text: str | None = None
    selected_action_id: str | None = None
    messages: list[tuple[str, str]] = field(default_factory=list)
    next_scene_id: str | None = None
    scene_changed: bool = False
    should_exit: bool = False
    events: list[CombatEvent] = field(default_factory=list)
    decision: dict[str, object] | None = None
    combat_state: dict[str, object] | None = None
