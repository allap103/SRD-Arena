"""PyTorch candidate policy with shared entity processing and a value baseline."""

from collections.abc import Callable
from typing import Any, Literal

import torch
from torch import Tensor, nn
from torch.distributions import Categorical

from srd_arena.frontends.rl.encoding import (
    ACTION_FEATURES,
    ENTITY_FEATURES,
    GLOBAL_FEATURES,
    EncodedObservation,
)

MODEL_SCHEMA_ID = "entity-candidate-actor-critic-v1"


def select_device(requested: Literal["auto", "cpu", "cuda"]) -> torch.device:
    """Resolve auto on this process; explicit CUDA never silently falls back."""
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA was requested but PyTorch cannot access it; check driver/device access or use --device cpu"
        )
    device = torch.device(
        "cuda" if requested != "cpu" and torch.cuda.is_available() else "cpu"
    )
    # Check an actual operation, not just the driver's advertised availability.
    probe = torch.ones(2, device=device, requires_grad=True)
    torch.autograd.backward(probe.square().sum())
    if device.type == "cuda":
        torch.cuda.synchronize()
    return device


class CandidatePolicy(nn.Module):
    """Score each action from shared entity embeddings and public parameters.

    Variable candidate counts avoid a fixed output neuron for each action ID.
    Actor/target slots route to entity embeddings, never identity embeddings.
    """

    def __init__(self, hidden_size: int = 32) -> None:
        super().__init__()
        self.hidden_size = hidden_size
        self.entity = nn.Sequential(
            nn.Linear(len(ENTITY_FEATURES), hidden_size), nn.Tanh()
        )
        self.action = nn.Sequential(
            nn.Linear(len(ACTION_FEATURES), hidden_size), nn.Tanh()
        )
        self.actor = nn.Sequential(
            nn.Linear(len(GLOBAL_FEATURES) + 4 * hidden_size + 2, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, 1),
        )
        self.critic = nn.Sequential(
            nn.Linear(len(GLOBAL_FEATURES) + hidden_size, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, 1),
        )

    def forward(self, observation: EncodedObservation) -> tuple[Tensor, Tensor]:
        """Return masked action logits and the public-state value estimate."""
        device = next(self.parameters()).device
        global_features = torch.as_tensor(
            observation.global_features, dtype=torch.float32, device=device
        )
        entities = self.entity(
            torch.as_tensor(observation.entities, dtype=torch.float32, device=device)
        )
        entity_mask = torch.as_tensor(observation.entity_mask, device=device)
        pooled = (entities * entity_mask[:, None]).sum(dim=0) / entity_mask.sum().clamp(
            min=1
        )
        extended = torch.cat(
            (entities, torch.zeros((1, self.hidden_size), device=device))
        )
        # -1 routes to the appended unknown/not-applicable embedding.
        actors = torch.as_tensor(observation.actor_slots, device=device)
        targets = torch.as_tensor(observation.target_slots, device=device)
        actions = self.action(
            torch.as_tensor(observation.actions, dtype=torch.float32, device=device)
        )
        count = len(observation.actions)
        features = torch.cat(
            (
                global_features.expand(count, -1),
                pooled.expand(count, -1),
                extended[actors],
                extended[targets],
                actions,
                (actors >= 0)[:, None],
                (targets >= 0)[:, None],
            ),
            dim=1,
        )
        logits = self.actor(features).squeeze(-1)
        mask = torch.as_tensor(observation.action_mask, device=device)
        logits = logits.masked_fill(~mask, float("-inf"))
        value = self.critic(torch.cat((global_features, pooled))).squeeze(-1)
        return logits, value

    def choose(
        self,
        observation: EncodedObservation,
        *,
        greedy: bool = False,
        report: Callable[[dict[str, Any]], None] | None = None,
    ) -> int:
        """Select an admitted candidate without retaining an inference graph."""
        if not observation.action_mask.any():
            raise ValueError("Cannot choose from an empty action mask")
        with torch.no_grad():
            logits, value = self(observation)
            if not torch.isfinite(
                logits[torch.as_tensor(observation.action_mask, device=logits.device)]
            ).all():
                raise ValueError("Policy produced nonfinite logits")
            selected = int(
                (
                    logits.argmax() if greedy else Categorical(logits=logits).sample()  # type: ignore[no-untyped-call]
                ).item()
            )

            if report is not None:
                distribution = Categorical(logits=logits)
                probs = distribution.probs.detach().cpu()
                top = probs.topk(min(5, int(observation.action_mask.sum())))
                report(
                    {
                        "mode": "greedy" if greedy else "sample",
                        "selected_index": selected,
                        "selected_probability": float(probs[selected]),
                        "value_estimate": float(value.detach().cpu()),
                        "entropy": float(distribution.entropy().detach().cpu()),  # type: ignore[no-untyped-call]
                        "candidate_count": int(observation.action_mask.sum()),
                        "top_choices": [
                            {"index": int(i), "probability": float(p)}
                            for i, p in zip(top.indices, top.values, strict=True)
                        ],
                    }
                )
            return selected
