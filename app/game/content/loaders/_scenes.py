from pathlib import Path

from ..schemas import SceneSchema
from ...models.choice import Choice, Effects, ItemRequirement, Outcome, Requirements, SkillTest
from ...models.scene import (
    Behavior,
    Encounter,
    EncounterEnemy,
    EncounterResolution,
    EncounterTeam,
    FleeResolution,
    Grid,
    Position,
    Scene,
)
from ._shared import _load_json


def _build_requirements(requirements) -> Requirements | None:
    if requirements is None:
        return None

    return Requirements(
        items=[
            ItemRequirement(
                id=item.id,
                quantity=item.quantity,
                missing_message=item.missing_message,
                consume=item.consume,
            )
            for item in requirements.items
        ]
    )


def _build_effects(effects) -> Effects | None:
    if effects is None:
        return None

    def build_outcome(outcome) -> Outcome | None:
        if outcome is None:
            return None
        return Outcome(
            message=outcome.message,
            next_scene=outcome.next_scene,
            gain_item=outcome.gain_item,
            lose_item=outcome.lose_item,
            damage=outcome.damage,
            healing=outcome.healing,
        )

    return Effects(
        on_success=build_outcome(effects.on_success),
        on_failure=build_outcome(effects.on_failure),
    )


def _build_test(test) -> SkillTest | None:
    if test is None:
        return None

    return SkillTest(
        skill=test.skill,
        difficulty=test.difficulty,
        repeatable=test.repeatable,
        effects=_build_effects(test.effects),
    )


def _build_position(position) -> Position:
    return Position(x=position.x, y=position.y)


def _build_encounter(encounter) -> Encounter | None:
    if encounter is None:
        return None

    enemy_ids = [enemy.actor_id for enemy in encounter.enemies]
    teams = (
        [
            EncounterTeam(
                id=team.id,
                name=team.name,
                members=list(team.members),
                controller=team.controller,
            )
            for team in encounter.teams
        ]
        if encounter.teams
        else [
            EncounterTeam(
                id="player",
                name="Player",
                members=["player"],
                controller="user",
            ),
            EncounterTeam(
                id="enemies",
                name="Enemies",
                members=enemy_ids,
                controller="ai",
            ),
        ]
    )
    return Encounter(
        grid=Grid(width=encounter.grid.width, height=encounter.grid.height),
        player_start=_build_position(encounter.player_start),
        enemies=[
            EncounterEnemy(
                actor_id=enemy.actor_id,
                start=_build_position(enemy.start),
                behavior=Behavior(
                    type=enemy.behavior.type,
                    anchor=_build_position(enemy.behavior.anchor)
                    if enemy.behavior.anchor
                    else None,
                    radius=enemy.behavior.radius,
                    path=[
                        _build_position(path_position)
                        for path_position in enemy.behavior.path
                    ],
                ),
            )
            for enemy in encounter.enemies
        ],
        teams=teams,
        victory=EncounterResolution(
            next_scene=encounter.victory.next_scene,
            message=encounter.victory.message,
        ),
        defeat=EncounterResolution(
            next_scene=encounter.defeat.next_scene,
            message=encounter.defeat.message,
        ),
        flee=FleeResolution(
            next_scene=encounter.flee.next_scene,
            allowed=encounter.flee.allowed,
        )
        if encounter.flee
        else None,
    )


def load_scene(path: str | Path) -> Scene:
    schema = SceneSchema.model_validate(_load_json(path))
    choices = [
        Choice(
            choice_text=choice_text,
            next_scene=choice.next_scene,
            message=choice.message,
            requirements=_build_requirements(choice.requirements),
            test=_build_test(choice.test),
        )
        for choice_text, choice in schema.choices.items()
    ]
    return Scene(
        id=schema.id,
        type=schema.type,
        text=schema.text,
        choices=choices,
        encounter=_build_encounter(schema.encounter),
    )
