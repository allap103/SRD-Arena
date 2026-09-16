"""Versioned local combat records derived only from spectator boundaries."""

from collections import Counter
from collections.abc import Mapping
from typing import Any, TextIO

from srd_arena.engine.api import GameplayObservation
from srd_arena.frontends.headless.serialization import canonical_json, json_value
from srd_arena.frontends.rl.actions import Candidate
from srd_arena.frontends.rl.diagnostics import CommandBoundary

DIAGNOSTIC_SCHEMA = "combat-diagnostics-v1"


def creature_states(snapshot: GameplayObservation) -> dict[str, Any]:
    """Keep compact combat facts without duplicating spell catalogs or inventory."""
    return {
        c.combat.creature_ref: {
            "name": c.combat.name,
            "team": c.combat.team_id,
            "health": c.combat.health,
            "max_health": c.combat.max_health,
            "temporary_hit_points": c.combat.temporary_hit_points,
            "alive": c.combat.is_alive,
            "position": json_value(c.combat.position),
            "actions_remaining": c.actions_remaining,
            "bonus_action_available": c.bonus_action_available,
            "reaction_available": c.combat.reaction_available,
            "movement_remaining_feet": c.combat.movement_remaining_feet,
            "spell_slots": json_value(c.combat.spell_slots),
            "resources": json_value(c.combat.resource_pools),
            "conditions": list(c.combat.effective_conditions),
            "concentrating_on": list(c.concentrating_on),
        }
        for c in snapshot.creatures
    }


class EpisodeRecorder:
    """Aggregate all combatants, optionally streaming detailed command records.

    Acceptance is a command-level fact. Effects retain their original event,
    action and frame IDs; no causal link is inferred from state differences.
    """

    def __init__(self, episode: int, stream: TextIO | None = None) -> None:
        self.episode = episode
        self.stream = stream
        self.sequence = 0
        self.history_count = 0
        self.rounds = 0
        self.turns: set[tuple[int, str | None]] = set()
        self.actions: Counter[tuple[str, str, str]] = Counter()
        self.rejections: Counter[str] = Counter()
        self.event_counts: Counter[str] = Counter()
        self.creatures: dict[str, Any] = {}
        self.pending_policy: dict[str, Any] | None = None

    def record_choice(
        self, selection: dict[str, Any], choices: tuple[Candidate, ...]
    ) -> None:
        """Attach readable candidate semantics without changing model inputs."""

        def describe(index: int) -> dict[str, Any]:
            c = choices[index]
            return {
                "kind": c.kind,
                "spell": c.spell.spell_id if c.spell else None,
                "target": c.target_ref,
                "aim": c.aim,
                "amount": c.amount,
                "command": json_value(c.command),
            }

        selection["selected"] = describe(selection["selected_index"])
        for option in selection.get("top_choices", []):
            option.update(describe(option["index"]))
        self.pending_policy = selection

    def record(self, boundary: CommandBoundary) -> None:
        """Consume one existing snapshot boundary without observing the engine."""
        before, after = boundary.before, boundary.after
        encounter = before.game.encounter
        round_number = encounter.round_number if encounter else 0
        self.rounds = max(self.rounds, round_number)
        actor = encounter.decision.creature_ref if encounter else None
        decision_id = encounter.decision.id if encounter else None
        decision_kind = encounter.decision.kind if encounter else None
        if before.active_turn_ref is not None:
            self.turns.add((round_number, before.active_turn_ref))
        events = after.history[self.history_count :]
        self.history_count = len(after.history)
        for event in events:
            self.event_counts[event.type] += 1
        for c in after.creatures:
            ref = c.combat.creature_ref
            stats = self.creatures.setdefault(
                ref,
                {
                    "name": c.combat.name,
                    "team": c.combat.team_id,
                    "commands": 0,
                    "accepted": 0,
                    "rejected": 0,
                    "wait_commands": 0,
                    "attack_events": 0,
                    "spell_cast_events": 0,
                    "recorded_attack_damage": 0,
                    "recorded_spell_damage": 0,
                    "recorded_spell_damage_to_allies": 0,
                    "recorded_spell_damage_to_enemies": 0,
                    "health_start": c.combat.health,
                },
            )
            stats["health_end"] = c.combat.health
            stats["alive_end"] = c.combat.is_alive
            stats["spell_slots_remaining"] = sum(
                s.remaining for s in c.combat.spell_slots
            )
        for event in events:
            if event.creature_ref not in self.creatures:
                continue
            stats = self.creatures[event.creature_ref]
            if event.type == "attack_resolved":
                stats["attack_events"] += 1
                damage = event.data.get("damage")
                if isinstance(damage, (float, int)):
                    stats["recorded_attack_damage"] += damage
            elif event.type == "spell_cast":
                stats["spell_cast_events"] += 1
                # Use only the full per-target list, never both its legacy first
                # detail alias and the full list (which would double count).
                details = event.data.get("damage_roll_details", ())
                if isinstance(details, (tuple, list)):
                    for detail in details:
                        if not isinstance(detail, Mapping):
                            continue
                        damage = detail.get("applied_damage")
                        if not isinstance(damage, (int, float)):
                            continue
                        stats["recorded_spell_damage"] += damage
                        target = self.creatures.get(str(detail.get("target_ref")))
                        if target is not None:
                            relation = (
                                "allies"
                                if stats["team"] == target["team"]
                                else "enemies"
                            )
                            stats["recorded_spell_damage_to_" + relation] += damage
        selected_id = (
            getattr(boundary.command, "action_id", None)
            if boundary.command is not None
            else boundary.update.selected_action_id
            if boundary.update
            else None
        )
        action = next(
            (a for a in before.game.scene.action_details if a.id == selected_id), None
        )
        kind = (
            action.kind
            if action
            else type(boundary.command).__name__
            if boundary.command
            else "automatic"
        )
        # Source identity groups aimed variants without parsing opaque action IDs.
        name = (
            (action.source_label or action.preferred_attack_name or action.kind)
            if action
            else (boundary.update.selected_choice_text if boundary.update else kind)
        )
        label = action.label if action else name
        if boundary.controller != "initial":
            self.sequence += 1
            result = "rejected" if boundary.rejection else "accepted"
            if actor in self.creatures:
                stats = self.creatures[actor]
                stats["commands"] += 1
                stats[result] += 1
                stats["wait_commands"] += kind == "wait" and result == "accepted"
            self.actions[(actor or "unknown", str(name), result)] += 1
            if boundary.rejection:
                self.rejections[boundary.rejection] += 1
        if self.stream is not None:
            payload = {
                "schema": DIAGNOSTIC_SCHEMA,
                "episode": self.episode,
                "sequence": self.sequence,
                "controller": boundary.controller,
                "round": round_number,
                "turn_actor": before.active_turn_ref,
                "actor": actor,
                "decision_id": decision_id,
                "decision_kind": decision_kind,
                "action_id": selected_id,
                "kind": kind,
                "name": name,
                "label": label,
                "command": json_value(boundary.command),
                "accepted": None
                if boundary.controller == "initial"
                else boundary.rejection is None,
                "rejection": boundary.rejection,
                "command_seconds": boundary.seconds,
                "policy": self.pending_policy
                if boundary.controller == "model"
                else None,
                "before": creature_states(before),
                "after": creature_states(after),
                "events": [
                    {
                        "seq": e.seq,
                        "type": e.type,
                        "actor": e.creature_ref,
                        "action_id": e.action_id,
                        "frame_id": e.frame_id,
                        "data": json_value(e.data),
                    }
                    for e in events
                ],
            }
            self.stream.write(canonical_json(payload) + "\n")
            self.stream.flush()
        if boundary.controller == "model":
            self.pending_policy = None

    def summary(self) -> dict[str, Any]:
        """Return one deterministic aggregate, including creatures that never acted."""
        return {
            "schema": DIAGNOSTIC_SCHEMA,
            "episode": self.episode,
            "rounds_reached": self.rounds,
            "turns_observed": len(self.turns),
            "commands": self.sequence,
            "rejection_reasons": dict(self.rejections),
            "event_counts": dict(self.event_counts),
            "creatures": self.creatures,
            "actions": [
                {"actor": actor, "action": action, "result": result, "count": count}
                for (actor, action, result), count in sorted(self.actions.items())
            ],
            "trace_available": self.stream is not None,
        }
