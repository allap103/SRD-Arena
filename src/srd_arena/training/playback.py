"""Paced model playback using the same environment as training and evaluation."""

from typing import Literal

import torch

from srd_arena.engine.api import GameObservation, GameUpdate
from srd_arena.training.checkpoint import LoadedCheckpoint
from srd_arena.training.command_outcomes import command_outcome


class ModelPlayback:
    """Advance one model command or scripted action for a spectator.

    The GUI receives unrestricted snapshots. Model inference receives only the
    environment's encoded, policy-filtered arrays, including during interrupts.
    """

    def __init__(
        self,
        checkpoint: LoadedCheckpoint,
        *,
        sampling_seed: int = 123,
        mode: Literal["sample", "greedy"] = "sample",
    ) -> None:
        if sampling_seed < 0:
            raise ValueError("Sampling seed must be nonnegative")
        self.checkpoint = checkpoint
        self.environment = checkpoint.config.environment()
        self.sampling_seed = sampling_seed
        self.mode = mode
        self.status = ""
        self.reset()

    @property
    def finished(self) -> bool:
        """Return whether the episode completed or reached a configured limit."""
        return self.transition.terminated or self.transition.truncated

    def observe(self) -> GameObservation:
        """Return the normal GUI view, never used as the model input."""
        return self.environment.spectator_snapshot().game

    def reset(self) -> None:
        """Restart the saved combat seed and the selected sampling seed."""
        torch.manual_seed(self.sampling_seed)
        torch.set_num_threads(1)
        self.transition = self.environment.reset(
            seed=self.checkpoint.config.encounter_seed, advance_automatic=False
        )
        self.status = (
            "Ready — model controls " + self.checkpoint.config.perspective_creature
        )
        self._update_status()

    def advance(self) -> GameUpdate | None:
        """Resolve exactly one action, retaining journal events for GUI dice/logs."""
        if self.finished:
            return None
        before = self.environment.spectator_snapshot()
        selected_id = None
        selected_kind = None
        if self.environment.automatic_pending:
            encounter = before.game.encounter
            assert encounter is not None
            label = f"Scripted action: {encounter.decision.creature_ref}"
            self.transition = self.environment.advance_one_automatic()
        else:
            index = self.checkpoint.model.choose(
                self.transition.observation, greedy=self.mode == "greedy"
            )
            candidate = self.environment.prepare_action(
                index,
                lambda encoded, choices: self.checkpoint.model.choose(
                    encoded, greedy=self.mode == "greedy"
                ),
            )
            command = candidate.command
            selected_kind = candidate.kind
            selected_id = getattr(command, "action_id", None)
            # Human labels come from the spectator snapshot after selection;
            # they never influence the encoded observation or model choice.
            action = next(
                (a for a in before.game.scene.action_details if a.id == selected_id),
                None,
            )
            label = ("Model attempt: " if candidate.kind == "spell" else "Model: ") + (
                action.label if action else candidate.kind.replace("_", " ")
            )
            if candidate.aim is not None:
                label += f" at ({candidate.aim[0]:g}, {candidate.aim[1]:g})"
            if candidate.selected_refs:
                label += " → " + ", ".join(candidate.selected_refs)
            elif candidate.target_ref is not None:
                label += f" → {candidate.target_ref}"
            if candidate.amount is not None:
                label += f" ({candidate.amount})"
            self.transition = self.environment.step(
                candidate,
                expected_decision_id=self.transition.decision_id,
                advance_automatic=False,
            )
            if (
                selected_kind != "spell"
                and self.transition.info["rejection"] is not None
            ):
                label += f" — rejected ({self.transition.info['rejection']})"
        after = self.environment.spectator_snapshot()
        events = after.history[len(before.history) :]
        if selected_kind == "spell":
            rejection = self.transition.info["rejection"]
            label += " — " + command_outcome(
                kind="spell",
                selected_id=selected_id,
                rejection=str(rejection) if rejection is not None else None,
                events=(
                    {"type": e.type, "action_id": e.action_id, "data": e.data}
                    for e in events
                ),
            )
        else:
            for event in events:
                if event.type == "spell_cast":
                    label += (
                        f" | Cast resolved: {event.data.get('spell_name', 'spell')}"
                    )
                    if not event.data.get("success"):
                        label += " (no immediate effect)"
        self.status = label
        self._update_status()
        return GameUpdate(
            observation=after.game,
            messages=(("info", label),),
            events=events,
            selected_action_id=selected_id,
            selected_choice_text=label,
            should_exit=False,
        )

    def _update_status(self) -> None:
        if self.transition.terminated:
            winner = self.transition.info["winning_team_id"]
            self.status = (
                f"Finished — winner: {winner}"
                if winner is not None
                else "Finished — draw"
            )
        elif self.transition.truncated:
            self.status = f"Stopped — {self.transition.info['truncation_reason']}"
        self.status += f" | decisions {self.transition.info['decisions']}, engine steps {self.transition.info['engine_steps']}"
