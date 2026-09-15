"""Terminal-only task rewards, independent of optional diagnostic metrics."""

from srd_arena.frontends.headless.adapter import EpisodeStatus

REWARD_SCHEMA_ID = "terminal-team-outcome-v1"


def terminal_reward(status: EpisodeStatus, team_id: str) -> float:
    """Score wins +1, losses -1, and active/draw/truncated states zero."""
    if not status.terminated or status.winning_team_id is None:
        return 0.0
    return 1.0 if status.winning_team_id == team_id else -1.0
