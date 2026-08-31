from types import SimpleNamespace
from typing import cast

from srd_arena.domain.capabilities import (
    AutomaticResolution,
    CapabilityDefinition,
    CapabilityStep,
    CapabilityTarget,
    ConditionEffect,
    EffectDuration,
    FixedDifficultyClass,
    Outcome,
    OutcomeStage,
    RepeatSave,
    SavingThrowResolution,
    TargetCount,
)
from srd_arena.domain.encounters.actions.capability_support import (
    capability_runtime_issue,
    capability_target_runtime_issue,
)
from srd_arena.domain.encounters.actions.eligibility_rules.models import (
    ActionEligibility,
    EligibilityFailure,
)
from srd_arena.domain.encounters.actions.eligibility_rules.spells import (
    SpellActionRule,
)
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.spells import Spell
from srd_arena.domain.spells.rules import spell_action_payload
from srd_arena.engine.action_observations import observe_scene
from srd_arena.engine.queries import SessionRead
from srd_arena.engine.session_queries import _action_option


def test_runtime_support_rejects_non_creature_area_semantics() -> None:
    objects = capability_target_runtime_issue(
        CapabilityTarget("area", affected_entities="objects")
    )
    mixed = capability_target_runtime_issue(
        CapabilityTarget("area", affected_entities="creatures_and_objects")
    )

    assert objects is not None
    assert objects.code == "unsupported_target_entities"
    assert mixed is not None
    assert mixed.code == "unsupported_target_entities"


def test_runtime_support_rejects_unimplemented_target_qualifiers() -> None:
    targets_and_codes = (
        (
            CapabilityTarget("area", occupants="allies"),
            "unsupported_area_occupants",
        ),
        (
            CapabilityTarget("area", origin="point", excludes_source=True),
            "unsupported_source_exclusion",
        ),
        (
            CapabilityTarget(
                "creature",
                count=TargetCount(minimum=2, maximum=3),
                selection="choose_up_to",
            ),
            "unsupported_target_minimum",
        ),
        (
            CapabilityTarget(
                "creature",
                count=TargetCount(maximum=2),
                selection="choose",
            ),
            "unsupported_exact_target_count",
        ),
    )

    for target, expected_code in targets_and_codes:
        issue = capability_target_runtime_issue(target)
        assert issue is not None
        assert issue.code == expected_code


def test_runtime_support_checks_nested_targets_and_repeat_save_durations() -> None:
    duration = EffectDuration(
        "until_event",
        events=("target_hit", "target_saves"),
        event_match="all",
    )
    repeated_save = RepeatSave(
        "end_of_turn",
        automatic_success_after=duration,
    )
    definition = CapabilityDefinition(
        CapabilityTarget("creature"),
        SavingThrowResolution(
            "wisdom",
            FixedDifficultyClass(15),
            (OutcomeStage((), (repeated_save,)),),
        ),
        follow_ups=(
            CapabilityStep(
                CapabilityTarget("area", occupants="all"),
                AutomaticResolution(Outcome()),
            ),
        ),
    )

    issue = capability_runtime_issue(definition)

    assert issue is not None
    assert issue.code == "unsupported_all_event_duration"


def test_runtime_support_rejects_any_event_and_spell_turn_durations() -> None:
    any_event = EffectDuration(
        "until_event",
        events=("target_takes_damage",),
    )
    turn_relative = EffectDuration(
        "end_of_turn",
        creature="target",
    )

    any_event_definition = CapabilityDefinition(
        CapabilityTarget("creature"),
        AutomaticResolution(
            Outcome((ConditionEffect("frightened", duration=any_event),))
        ),
    )
    turn_definition = CapabilityDefinition(
        CapabilityTarget("creature"),
        AutomaticResolution(
            Outcome((ConditionEffect("frightened", duration=turn_relative),))
        ),
    )

    any_event_issue = capability_runtime_issue(any_event_definition)
    turn_issue = capability_runtime_issue(turn_definition)

    assert any_event_issue is not None
    assert any_event_issue.code == "unsupported_event_duration"
    assert turn_issue is not None
    assert turn_issue.code == "unsupported_turn_relative_duration"
    assert (
        capability_runtime_issue(
            turn_definition,
            supports_turn_relative_durations=True,
        )
        is None
    )


def test_runtime_support_checks_follow_up_target_semantics_first() -> None:
    definition = CapabilityDefinition(
        CapabilityTarget("self"),
        AutomaticResolution(Outcome()),
        follow_ups=(
            CapabilityStep(
                CapabilityTarget("area", occupants="allies"),
                AutomaticResolution(Outcome()),
            ),
        ),
    )

    issue = capability_runtime_issue(definition)

    assert issue is not None
    assert issue.code == "unsupported_area_occupants"


def test_runtime_support_accepts_current_creature_and_timed_effect_semantics() -> None:
    definition = CapabilityDefinition(
        CapabilityTarget(
            "creature",
            range_feet=60,
            line_of_sight=True,
            disposition="enemy",
        ),
        AutomaticResolution(
            Outcome(
                (
                    ConditionEffect(
                        "stunned",
                        duration=EffectDuration("timed", 1, "minute"),
                    ),
                )
            )
        ),
    )

    assert capability_runtime_issue(definition) is None


def test_spell_eligibility_rejects_unsupported_semantics_before_resolution() -> None:
    definition = CapabilityDefinition(
        CapabilityTarget("area", affected_entities="objects"),
        AutomaticResolution(Outcome()),
    )
    spell = Spell(
        "animate_objects",
        "Animate Objects",
        "TEST",
        5,
        definition=definition,
    )
    spellcasting = SimpleNamespace(learned_spells=(spell,))
    state = SimpleNamespace(
        creatures={
            "mage": SimpleNamespace(creature=SimpleNamespace(spellcasting=spellcasting))
        }
    )
    action = EncounterAction(
        "Cast Animate Objects",
        "spell",
        value=spell_action_payload("animate_objects"),
        id="mage-spell-animate_objects",
        creature_ref="mage",
    )

    failure = SpellActionRule().check(cast(EncounterState, state), "mage", action)

    assert failure is not None
    assert failure.code == "unsupported_target_entities"
    assert failure.message == "Areas that affect objects are not executable yet."


def test_unsupported_eligibility_is_advertised_as_unimplemented() -> None:
    action = EncounterAction(
        "Cast Animate Objects",
        "spell",
        id="animate-objects",
        creature_ref="mage",
    )
    eligibility = ActionEligibility(
        (
            EligibilityFailure(
                "unsupported_target_entities",
                "Areas that affect objects are not executable yet.",
            ),
        )
    )

    option = _action_option(action, eligibility)

    assert option.enabled is False
    assert option.availability == "unimplemented"

    read = SessionRead(
        scene_id="fight",
        scene_text=None,
        action_options=(option,),
        encounter_state=None,
        completion_message=None,
        team_ids=(),
        creature_labels={},
        creature_team_ids={},
        item_names={},
        requires_automatic_advance=False,
    )
    observed = observe_scene(read).action_details[0]

    assert observed.availability == "unimplemented"
    assert observed.reasons[0].code == "unsupported_target_entities"
    assert observed.reasons[0].message == (
        "Areas that affect objects are not executable yet."
    )
