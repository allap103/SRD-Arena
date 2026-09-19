"""Rate-limited episode progress for terminals and structured run logs."""

import math
import sys
from collections.abc import Callable
from time import perf_counter
from typing import TextIO

from srd_arena.engine.api import GameplayObservation
from srd_arena.frontends.headless.serialization import canonical_json


class EpisodeProgress:
    """Report completed work at engine/learner boundaries without extra snapshots.

    Timing uses a monotonic wall clock. Reports are flushed to stderr and JSONL;
    they are not a background heartbeat during a blocked engine or CUDA call.
    """

    def __init__(
        self,
        episode: int,
        episodes: int,
        stream: TextIO,
        *,
        interval: float = 2.0,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        if not math.isfinite(interval) or interval < 0:
            raise ValueError("Progress interval must be finite and nonnegative")
        self.episode = episode
        self.episodes = episodes
        self.stream = stream
        self.interval = interval
        self.clock = clock
        self.started = self.last_report = clock()
        self.phase = "reset"
        self.round = self.decisions = self.engine_steps = 0
        self.update_samples = self.update_total = 0
        self._combat_started = False
        self._turn: tuple[int, str] | None = None
        self._turn_name = ""
        self._turn_was_alive = True
        self._turn_started = self.started
        self._turn_decisions = self._turn_steps = 0
        self.inference_seconds = self.environment_seconds = self.reset_seconds = 0.0

    def report(self, phase: str | None = None, *, force: bool = False) -> None:
        """Emit current counters when due, or on a forced lifecycle boundary."""
        if phase is not None:
            self.phase = phase
        now = self.clock()
        if self.interval == 0 or (not force and now - self.last_report < self.interval):
            return
        self.last_report = now
        elapsed = now - self.started
        record = {
            "event": "progress",
            "episode": self.episode,
            "episodes": self.episodes,
            "phase": self.phase,
            "elapsed_seconds": elapsed,
            "round": self.round,
            "decisions": self.decisions,
            "engine_steps": self.engine_steps,
            "update_samples": self.update_samples,
            "update_total": self.update_total,
        }
        self.stream.write(canonical_json(record) + "\n")
        self.stream.flush()
        detail = (
            f" | samples {self.update_samples}/{self.update_total}"
            if self.phase == "update"
            else ""
        )
        print(
            f"Episode {self.episode}/{self.episodes} | {elapsed:.1f}s | {self.phase}"
            f" | round {self.round} | decisions {self.decisions}"
            f" | engine steps {self.engine_steps}{detail}",
            file=sys.stderr,
            flush=True,
        )

    def engine_progress(
        self, snapshot: GameplayObservation, decisions: int, steps: int
    ) -> None:
        """Observe active initiative turns, keeping reaction decisions inside their turn."""
        encounter = snapshot.game.encounter
        if encounter is None:
            return
        self.round, self.decisions, self.engine_steps = (
            encounter.round_number,
            decisions,
            steps,
        )
        current = (
            (self.round, snapshot.active_turn_ref) if snapshot.active_turn_ref else None
        )
        if self._turn is not None and (
            current != self._turn or snapshot.game.completion
        ):
            self._finish_turn(
                "encounter_ended" if snapshot.game.completion else "next_turn"
            )
        if snapshot.game.completion:
            self._turn = None
        elif (
            current is not None
            and current != self._turn
            and (self._combat_started or encounter.decision.kind == "turn")
        ):
            self._combat_started = True
            self._turn = current
            creature = next(
                c.combat
                for c in snapshot.creatures
                if c.combat.creature_ref == current[1]
            )
            self._turn_name = creature.name
            self._turn_was_alive = creature.is_alive
            self._turn_started = self.clock()
            self._turn_decisions, self._turn_steps = decisions, steps
        self.report()

    def _finish_turn(self, reason: str) -> None:
        """Flush every observed completed turn, independently of the progress interval."""
        assert self._turn is not None
        now = self.clock()
        round_number, creature_ref = self._turn
        record = {
            "event": "turn_completed" if self._turn_was_alive else "turn_skipped",
            "episode": self.episode,
            "round": round_number,
            "creature_ref": creature_ref,
            "creature_name": self._turn_name,
            "reason": reason,
            "elapsed_seconds": now - self.started,
            "turn_seconds": now - self._turn_started,
            "decisions": self.decisions - self._turn_decisions,
            "engine_steps": self.engine_steps - self._turn_steps,
        }
        self.stream.write(canonical_json(record) + "\n")
        self.stream.flush()
        status = "completed" if self._turn_was_alive else "skipped (defeated)"
        ending = " (encounter ended)" if reason == "encounter_ended" else ""
        print(
            f"Episode {self.episode}/{self.episodes} | {now - self.started:.1f}s"
            f" | round {round_number} | {self._turn_name} [{creature_ref}] turn {status}"
            f" | {now - self._turn_started:.2f}s"
            f" | engine steps {record['engine_steps']}{ending}",
            file=sys.stderr,
            flush=True,
        )
        self._turn = None

    def optimization_progress(self, completed: int, total: int) -> None:
        """Report completed trajectory samples during the gradient update."""
        self.update_samples, self.update_total = completed, total
        self.report("update")

    def timings(self) -> dict[str, float]:
        """Return cumulative rollout timing for the completed-episode metrics."""
        return {
            "reset_seconds": self.reset_seconds,
            "inference_seconds": self.inference_seconds,
            "environment_seconds": self.environment_seconds,
        }
