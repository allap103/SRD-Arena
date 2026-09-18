"""Configurable terminal scores, isolated from the model's observation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from srd_arena.engine.api import GameplayObservation
from srd_arena.frontends.headless.adapter import EpisodeStatus

REWARD_SCHEMA_ID = "terminal-party-outcome-v2"


class RewardWeights(BaseModel):
    """Weight outcomes, first falls, and normalized victory-only preservation."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, allow_inf_nan=False
    )
    win: float = Field(default=1.0, ge=0)
    loss: float = Field(default=-1.0, le=0)
    draw: float = 0.0
    truncation: float = 0.0
    party_member_down: float = Field(default=-0.1, le=0)
    victory_health: float = Field(default=0.1, ge=0)
    victory_spell_slots: float = Field(default=0.0, ge=0)
    victory_class_resources: float = Field(default=0.0, ge=0)


def episode_outcome(
    status: EpisodeStatus, team_id: str
) -> Literal["active", "win", "loss", "draw", "truncated"]:
    """Classify the rules outcome independently of a configurable score's sign."""
    if status.truncated:
        return "truncated"
    if not status.terminated:
        return "active"
    if status.winning_team_id is None:
        return "draw"
    return "win" if status.winning_team_id == team_id else "loss"


def terminal_reward(status: EpisodeStatus, team_id: str) -> float:
    """Return the original win/loss-only baseline score."""
    return {"win": 1.0, "loss": -1.0}.get(episode_outcome(status, team_id), 0.0)


def fraction(remaining: int, maximum: int) -> float:
    """Normalize a resource family; absent capacity earns no preservation bonus."""
    return min(1.0, max(0.0, remaining / maximum)) if maximum > 0 else 0.0


class EpisodeReward:
    """Track each starting party member's first fall, even across scripted turns."""

    def __init__(
        self, initial: GameplayObservation, team_id: str, weights: RewardWeights
    ) -> None:
        self.team_id = team_id
        self.weights = weights
        self.party_refs = frozenset(
            c.combat.creature_ref
            for c in initial.creatures
            if c.combat.team_id == team_id
        )
        self._standing_at_start = frozenset(
            c.combat.creature_ref
            for c in initial.creatures
            if c.combat.creature_ref in self.party_refs and c.combat.health > 0
        )
        self.fallen: set[str] = set()
        self._history_count = len(initial.history)

    def observe(self, snapshot: GameplayObservation) -> None:
        """Record falls once without making rewards depend on diagnostic logging."""
        self.fallen.update(
            c.combat.creature_ref
            for c in snapshot.creatures
            if c.combat.creature_ref in self._standing_at_start and c.combat.health <= 0
        )
        self.fallen.update(
            e.creature_ref
            for e in snapshot.history[self._history_count :]
            if e.type == "creature_defeated"
            and e.creature_ref in self._standing_at_start
        )
        self._history_count = len(snapshot.history)

    def components(
        self, status: EpisodeStatus, snapshot: GameplayObservation
    ) -> dict[str, float]:
        """Return additive terminal terms; intermediate transitions score zero."""
        outcome = episode_outcome(status, self.team_id)
        terms = dict.fromkeys(
            (
                "outcome",
                "party_member_down",
                "victory_health",
                "victory_spell_slots",
                "victory_class_resources",
            ),
            0.0,
        )
        if outcome == "active":
            return terms
        weights = self.weights
        terms["outcome"] = {
            "win": weights.win,
            "loss": weights.loss,
            "draw": weights.draw,
            "truncated": weights.truncation,
        }[outcome]
        terms["party_member_down"] = weights.party_member_down * len(self.fallen)
        if outcome == "win":
            party = [
                c.combat
                for c in snapshot.creatures
                if c.combat.creature_ref in self.party_refs
            ]
            slots = [s for c in party for s in c.spell_slots]
            resources = [
                p for c in party for p in c.resource_pools if p.kind == "feature_uses"
            ]
            terms["victory_health"] = weights.victory_health * fraction(
                sum(max(0, c.health) for c in party), sum(c.max_health for c in party)
            )
            terms["victory_spell_slots"] = weights.victory_spell_slots * fraction(
                sum(s.remaining for s in slots), sum(s.maximum for s in slots)
            )
            terms["victory_class_resources"] = (
                weights.victory_class_resources
                * fraction(
                    sum(p.remaining for p in resources),
                    sum(p.maximum for p in resources),
                )
            )
        return terms
