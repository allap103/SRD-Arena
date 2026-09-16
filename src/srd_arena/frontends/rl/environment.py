"""Single-controller environment over the existing public headless API."""

from collections.abc import Callable
from dataclasses import dataclass

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    FilteredObservation,
    GameplayObservation,
    ObservationPolicy,
    PolicyProjector,
)
from srd_arena.frontends.headless.adapter import (
    EpisodeTruncationReason,
    HeadlessGameAdapter,
)
from srd_arena.frontends.rl.actions import Candidate, candidates
from srd_arena.frontends.rl.encoding import EncodedObservation, Encoder
from srd_arena.frontends.rl.rewards import terminal_reward


@dataclass(frozen=True)
class Transition:
    """One model decision boundary; info is for diagnostics, never policy input."""

    observation: EncodedObservation
    reward: float
    terminated: bool
    truncated: bool
    decision_id: str
    info: dict[str, object]


class ArenaEnvironment:
    """Control one fixed creature; advance scripted turns and stop for interrupts.

    This small in-process reset/step API is intentionally not a Gymnasium
    implementation yet. Each step is one model command attempt. Rejections
    consume the decision budget but not the accepted-engine-step budget, so
    an unsuccessful or looping policy cannot block an episode forever.
    """

    def __init__(
        self,
        *,
        encounter_id: str,
        perspective_creature: str,
        policy: ObservationPolicy,
        max_decisions: int = 200,
        max_engine_steps: int = 1000,
        max_rounds: int = 100,
        max_entities: int = 10,
        max_candidates: int = 16384,
    ) -> None:
        if (
            min(
                max_decisions,
                max_engine_steps,
                max_rounds,
                max_entities,
                max_candidates,
            )
            < 1
        ):
            raise ValueError("Environment capacities and limits must be positive")
        policy.validate_support()
        self.encounter_id = encounter_id
        self.perspective_creature = perspective_creature
        self.policy = policy
        self.max_decisions = max_decisions
        self.max_engine_steps = max_engine_steps
        self.max_rounds = max_rounds
        self.max_entities = max_entities
        self.max_candidates = max_candidates
        self._adapter = HeadlessGameAdapter(EncounterCatalog())
        self._encoder: Encoder | None = None
        self._projector: PolicyProjector | None = None
        self._observation: FilteredObservation | None = None
        self._choices: tuple[Candidate, ...] = ()
        self._team = ""
        self._decisions = 0
        self._engine_steps = 0
        self._rejected = 0
        self._done = True
        self._limit: str | None = None
        # Optional diagnostics; never part of the observation or policy input.
        self.progress_callback: (
            Callable[[GameplayObservation, int, int], None] | None
        ) = None

    @property
    def choices(self) -> tuple[Candidate, ...]:
        """Expose the current command mapping for debugging, outside tensors."""
        return self._choices

    def reset(self, *, seed: int, advance_automatic: bool = True) -> Transition:
        """Start a reproducible episode and run to the first owned decision."""
        self._adapter.start_encounter(self.encounter_id, seed=seed)
        snapshot = self._adapter.observe_gameplay()
        own = next(
            (
                c
                for c in snapshot.creatures
                if c.combat.creature_ref == self.perspective_creature
            ),
            None,
        )
        if own is None or not own.combat.is_alive:
            raise ValueError("Perspective must name a living creature")
        self._team = own.combat.team_id
        self._projector = PolicyProjector(self.policy, self.perspective_creature)
        self._encoder = Encoder(
            self._projector.project(snapshot), max_entities=self.max_entities
        )
        self._decisions = self._engine_steps = self._rejected = 0
        self._done = False
        self._limit = None
        return self._advance(advance_automatic=advance_automatic)

    def step(
        self,
        index: int,
        *,
        expected_decision_id: str | None = None,
        advance_automatic: bool = True,
    ) -> Transition:
        """Submit a candidate index and advance to the next external decision."""
        if self._done or self._observation is None:
            raise RuntimeError("Reset before stepping a finished environment")
        if type(index) is not int or not 0 <= index < len(self._choices):
            raise ValueError("Action index is outside the current candidate map")
        if (
            expected_decision_id is not None
            and expected_decision_id != self._observation.decision.id
        ):
            raise ValueError("Stale decision ID")
        choice = self._choices[index]
        result = self._adapter.submit_player(self._team, choice.command)
        self._decisions += 1
        rejection = None
        if result.accepted:
            self._engine_steps += 1
        else:
            self._rejected += 1
            assert result.failure is not None
            rejection = result.failure.code
        return self._advance(rejection=rejection, advance_automatic=advance_automatic)

    @property
    def automatic_pending(self) -> bool:
        """Return whether a scripted action is next in single-action playback."""
        return bool(
            not self._done
            and self._observation
            and self._observation.requires_automatic_advance
        )

    def spectator_snapshot(self) -> GameplayObservation:
        """Expose the unrestricted viewer snapshot separately from policy inputs."""
        return self._adapter.observe_gameplay()

    def advance_one_automatic(self) -> Transition:
        """Advance exactly one scripted action and retain the next visible boundary."""
        if not self.automatic_pending:
            raise RuntimeError("No automatic action is pending")
        self._adapter.advance_one_player_automatic_action(self._team)
        self._engine_steps += 1
        return self._advance(advance_automatic=False)

    def _advance(
        self, *, rejection: str | None = None, advance_automatic: bool = True
    ) -> Transition:
        assert self._projector is not None and self._encoder is not None
        while True:
            snapshot = self._adapter.observe_gameplay()
            if (
                self.progress_callback is not None
                and snapshot.game.encounter is not None
            ):
                self.progress_callback(
                    snapshot,
                    self._decisions,
                    self._engine_steps,
                )
            self._observation = self._projector.project(snapshot)
            if self._observation.completion is not None:
                break
            assert snapshot.game.encounter is not None
            if self._decisions >= self.max_decisions:
                self._limit = "decision_limit"
            elif self._engine_steps >= self.max_engine_steps:
                self._limit = "engine_step_limit"
            elif snapshot.game.encounter.round_number > self.max_rounds:
                self._limit = "round_limit"
            if self._limit:
                self._adapter.truncate(
                    EpisodeTruncationReason.TURN_LIMIT
                    if self._limit == "round_limit"
                    else EpisodeTruncationReason.STEP_LIMIT
                )
                break
            if not self._observation.requires_automatic_advance:
                if self._observation.decision.creature_ref != self.perspective_creature:
                    raise ValueError(
                        "An external decision belongs to another creature; this experiment controls only the fixed perspective"
                    )
                break
            if not advance_automatic:
                break
            self._adapter.advance_one_player_automatic_action(self._team)
            self._engine_steps += 1
        status = self._adapter.episode_status()
        self._done = status.terminated or status.truncated
        self._choices = (
            ()
            if self._done or self._observation.requires_automatic_advance
            else candidates(self._observation, maximum=self.max_candidates)
        )
        if not self._choices and not self._done and not self.automatic_pending:
            raise RuntimeError("No model action candidates at an external decision")
        info: dict[str, object] = {
            "decisions": self._decisions,
            "engine_steps": self._engine_steps,
            "rejected_commands": self._rejected,
            "rejection": rejection,
            "termination_reason": status.termination_reason,
            "truncation_reason": self._limit,
            "winning_team_id": status.winning_team_id,
        }
        if self._done:
            # Diagnostic outcome data is never sent to the encoder or model.
            allies = [
                c.combat for c in snapshot.creatures if c.combat.team_id == self._team
            ]
            info["resources"] = {
                "party_health": sum(c.health for c in allies),
                "party_max_health": sum(c.max_health for c in allies),
                "party_alive": sum(c.is_alive for c in allies),
                "spell_slots_remaining": sum(
                    slot.remaining for c in allies for slot in c.spell_slots
                ),
                "resource_units_remaining": sum(
                    pool.remaining for c in allies for pool in c.resource_pools
                ),
            }
        return Transition(
            self._encoder.encode(self._observation, self._choices),
            terminal_reward(status, self._team),
            status.terminated,
            status.truncated,
            self._observation.decision.id,
            info,
        )
