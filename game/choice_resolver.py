from dataclasses import dataclass, field

from .models.actor import Actor
from .models.choice import Choice, Effects, Outcome
from .models.scene import Scene
from .systems.roll import roll_die


@dataclass
class ChoiceResolution:
    next_scene_id: str
    messages: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ChoiceResolver:
    completed_tests: set[tuple[str, str]] = field(default_factory=set)

    def resolve(self, scene: Scene, choice: Choice, actor: Actor | None = None) -> ChoiceResolution:
        messages: list[tuple[str, str]] = []
        if choice.message:
            messages.append(("scene", choice.message))

        if not self._requirements_met(choice, actor, messages):
            return ChoiceResolution(next_scene_id=scene.id, messages=messages)

        self._consume_required_items(choice, actor)

        if choice.test is None:
            return ChoiceResolution(next_scene_id=choice.next_scene or scene.id, messages=messages)

        return self._resolve_test(scene, choice, actor, messages)

    def _requirements_met(
        self,
        choice: Choice,
        actor: Actor | None,
        messages: list[tuple[str, str]],
    ) -> bool:
        if choice.requirements is None:
            return True
        if actor is None:
            raise ValueError("An actor is required to resolve choice requirements.")

        for requirement in choice.requirements.items:
            if actor.inventory.count_item(requirement.id) < requirement.quantity:
                messages.append(
                    (
                        "system",
                        requirement.missing_message
                        or f"You need {requirement.quantity}x '{requirement.id}' to do that.",
                    )
                )
                return False

        return True

    def _consume_required_items(self, choice: Choice, actor: Actor | None) -> None:
        if choice.requirements is None or actor is None:
            return

        for requirement in choice.requirements.items:
            if requirement.consume:
                actor.inventory.remove_items(requirement.id, requirement.quantity)

    def _resolve_test(
        self,
        scene: Scene,
        choice: Choice,
        actor: Actor | None,
        messages: list[tuple[str, str]],
    ) -> ChoiceResolution:
        if actor is None:
            raise ValueError("An actor is required to resolve skill tests.")

        test = choice.test
        choice_key = (scene.id, choice.choice_text)
        if not test.repeatable and choice_key in self.completed_tests:
            messages.append(("choice", "You cannot repeat that test."))
            return ChoiceResolution(next_scene_id=scene.id, messages=messages)

        skill_value = getattr(actor.attributes, test.skill)
        modifier = actor.get_modifier(skill_value)
        roll = roll_die(20)
        total = roll + modifier
        messages.append(
            (
                "choice",
                f"Tested {test.skill}: rolled {roll} + modifier {modifier} = {total} against {test.difficulty}.",
            )
        )

        if total >= test.difficulty:
            self.completed_tests.add(choice_key)
            self._apply_effects(test.effects, success=True, actor=actor, messages=messages)
            return ChoiceResolution(next_scene_id=choice.next_scene or scene.id, messages=messages)

        self._apply_effects(test.effects, success=False, actor=actor, messages=messages)
        return ChoiceResolution(next_scene_id=scene.id, messages=messages)

    def _apply_effects(
        self,
        effects: Effects | None,
        success: bool,
        actor: Actor,
        messages: list[tuple[str, str]],
    ) -> None:
        if effects is None:
            return

        outcome = effects.on_success if success else effects.on_failure
        if outcome is None:
            return

        self._apply_outcome(outcome, actor, messages)

    def _apply_outcome(
        self,
        outcome: Outcome,
        actor: Actor,
        messages: list[tuple[str, str]],
    ) -> None:
        if outcome.message:
            messages.append(("scene", outcome.message))
        if outcome.gain_item:
            actor.add_item(outcome.gain_item)
            messages.append(("system", f"You gained '{outcome.gain_item}'."))
        if outcome.lose_item:
            actor.remove_item(outcome.lose_item)
            messages.append(("system", f"You lost '{outcome.lose_item}'."))
