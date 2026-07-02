from dataclasses import dataclass, field

from ..combat.encounter import CombatEvent


@dataclass
class SceneView:
    scene_id: str
    scene_text: str | None
    choices: list[str] = field(default_factory=list)
    action_details: list["ActionView"] = field(default_factory=list)


@dataclass
class ActionView:
    index: int
    id: str
    label: str
    kind: str
    actor_ref: str
    value: str | int | None = None
    cost: dict[str, int] = field(default_factory=dict)
    source_trigger_id: str | None = None


@dataclass
class TurnResult:
    scene: SceneView
    selected_index: int | None = None
    selected_choice_text: str | None = None
    selected_action_id: str | None = None
    messages: list[tuple[str, str]] = field(default_factory=list)
    next_scene_id: str | None = None
    scene_changed: bool = False
    should_exit: bool = False
    events: list[CombatEvent] = field(default_factory=list)
    decision: dict[str, object] | None = None
    combat_state: dict[str, object] | None = None
