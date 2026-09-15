"""Strict experiment configuration, separate from information disclosure."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from srd_arena.frontends.headless.config import load_policy, load_yaml_document
from srd_arena.frontends.headless.serialization import canonical_json
from srd_arena.frontends.rl.environment import ArenaEnvironment


class TrainingConfig(BaseModel):
    """Resolved settings for a terminal-reward single-encounter experiment."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, allow_inf_nan=False
    )
    schema_version: int = Field(ge=1, le=1)
    encounter: str
    perspective_creature: str
    observation_config: str
    encounter_seed: int = Field(ge=0)
    learner_seed: int = Field(ge=0)
    episodes: int = Field(ge=1)
    max_decisions: int = Field(ge=1)
    max_engine_steps: int = Field(ge=1)
    max_rounds: int = Field(ge=1)
    max_entities: int = Field(ge=1, le=128)
    max_candidates: int = Field(ge=1, le=65536)
    hidden_size: int = Field(ge=4, le=1024)
    learning_rate: float = Field(gt=0, le=1)
    entropy_coefficient: float = Field(ge=0, le=1)
    device: Literal["auto", "cpu", "cuda"]

    def environment(self) -> ArenaEnvironment:
        """Create an environment with the recorded disclosure and runner limits."""
        return ArenaEnvironment(
            encounter_id=self.encounter,
            perspective_creature=self.perspective_creature,
            policy=load_policy(Path(self.observation_config)),
            max_decisions=self.max_decisions,
            max_engine_steps=self.max_engine_steps,
            max_rounds=self.max_rounds,
            max_entities=self.max_entities,
            max_candidates=self.max_candidates,
        )


def load_training_config(path: Path) -> TrainingConfig:
    """Resolve observation-policy paths relative to the experiment file."""
    config = TrainingConfig.model_validate_json(
        canonical_json(load_yaml_document(path))
    )
    policy_path = (path.parent / config.observation_config).resolve()
    return config.model_copy(update={"observation_config": str(policy_path)})
