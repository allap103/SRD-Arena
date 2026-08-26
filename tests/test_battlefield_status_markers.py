from srd_arena.application.observations import (
    CreatureObservation,
    DecisionObservation,
    EncounterObservation,
    GridObservation,
    OngoingEffectObservation,
    PositionObservation,
)
from srd_arena.frontends.qt.ui.encounter.status_markers import (
    StatusMarkerHit,
    build_status_marker_specs,
    creature_name_label_rect,
    status_marker_hit_radius,
    status_marker_positions,
    status_marker_tooltip,
    status_tooltip_label_rect,
    target_allocation_badge_position,
)
from srd_arena.frontends.shared.battlefield import (
    build_battlefield_view,
)
from srd_arena.frontends.shared.conditions import effective_condition_names
from srd_arena.frontends.shared.models import (
    BattlefieldCreatureView,
    GridPositionView,
)


def _creature(
    creature_id: str,
    team_id: str,
    *,
    effective_conditions: list[str] | None = None,
) -> CreatureObservation:
    return CreatureObservation(
        creature_ref=creature_id,
        creature_id=creature_id,
        name=creature_id.replace("_", " ").title(),
        label=creature_id,
        token_image=None,
        team_id=team_id,
        position=PositionObservation(0, 0),
        health=10,
        max_health=10,
        is_alive=True,
        action_available=True,
        bonus_action_available=True,
        reaction_available=True,
        attacks_remaining=0,
        attacks_per_attack_action=1,
        movement_remaining=6,
        movement_total=6,
        movement_remaining_feet=30,
        movement_total_feet=30,
        effective_conditions=tuple(dict.fromkeys(effective_conditions or ())),
        spell_slots=(),
        feature_actions=(),
    )


def test_battlefield_view_groups_concentration_buffs_debuffs_and_conditions() -> None:
    encounter = EncounterObservation(
        encounter_id="status_test",
        grid=GridObservation(4, 4),
        round_number=1,
        decision=DecisionObservation(
            id="decision-1", creature_ref="caster", kind="turn"
        ),
        creatures=(
            _creature("caster", "heroes"),
            _creature(
                "ally",
                "heroes",
                effective_conditions=[
                    "paralyzed",
                    "incapacitated",
                    "incapacitated",
                ],
            ),
            _creature("enemy", "monsters"),
        ),
        initiative=(),
        ongoing_effects=(
            OngoingEffectObservation(
                "concentration", "beneficial", "caster", "bless", ("ally",), "Bless"
            ),
            OngoingEffectObservation(
                "concentration", "harmful", "enemy", "slow", ("ally",), "Slow"
            ),
            OngoingEffectObservation(
                "spell", "beneficial", "caster", "bless", ("ally",), "Bless"
            ),
            OngoingEffectObservation(
                "spell", "beneficial", None, "magic_zone", ("ally",), "Magic Zone"
            ),
            OngoingEffectObservation(
                "spell",
                "neutral",
                "caster",
                "ambiguous_effect",
                ("ally",),
                "Ambiguous Effect",
            ),
        ),
        team_ids=("heroes", "monsters"),
        targeting=None,
    )

    battlefield = build_battlefield_view(
        encounter,
        team_ids=("heroes", "monsters"),
    )
    creatures = {creature.creature_ref: creature for creature in battlefield.creatures}

    assert creatures["caster"].is_concentrating is True
    assert creatures["enemy"].is_concentrating is True
    assert creatures["ally"].is_concentrating is False
    assert creatures["ally"].buffs == ("Bless", "Magic Zone")
    assert creatures["ally"].debuffs == ("Slow",)
    assert creatures["ally"].conditions == ("paralyzed", "incapacitated")
    assert creatures["caster"].buffs == ()
    assert creatures["caster"].debuffs == ()


def test_status_marker_specs_have_fixed_corners_and_exact_tooltips() -> None:
    creature = BattlefieldCreatureView(
        creature_ref="target",
        creature_id="target",
        name="Target",
        label="Target",
        token_image=None,
        team_color="#ffffff",
        position=GridPositionView(0, 0),
        health=10,
        conditions=("prone", "incapacitated"),
        is_concentrating=True,
        buffs=("Bless",),
        debuffs=("Bane", "Slow"),
    )

    assert tuple(
        (spec.corner, spec.color, spec.tooltip)
        for spec in build_status_marker_specs(creature)
    ) == (
        ("top_left", "#2eaf62", "Buffs:\n- Bless"),
        ("top_right", "#e05252", "Debuffs:\n- Bane\n- Slow"),
        ("bottom_left", "#3887e8", "Concentrating on a spell"),
        (
            "bottom_right",
            "#efc84a",
            "Conditions:\n- Prone\n- Incapacitated",
        ),
    )


def test_status_markers_are_absent_without_statuses() -> None:
    creature = BattlefieldCreatureView(
        creature_ref="target",
        creature_id="target",
        name="Target",
        label="Target",
        token_image=None,
        team_color="#ffffff",
        position=GridPositionView(0, 0),
        health=10,
    )

    assert build_status_marker_specs(creature) == ()


def test_effective_conditions_override_raw_conditions_and_are_deduplicated() -> None:
    creature = _creature(
        "target",
        "heroes",
        effective_conditions=["prone", "prone", "incapacitated"],
    )

    assert effective_condition_names(creature) == ("prone", "incapacitated")


def test_status_marker_geometry_and_hit_testing_scale_with_the_board() -> None:
    positions, radius = status_marker_positions(
        cell_x=100.0,
        cell_y=200.0,
        center_x=136.0,
        center_y=236.0,
        token_radius=27.0,
        cell_size=72.0,
    )
    hits = [
        StatusMarkerHit(
            *positions["bottom_left"],
            status_marker_hit_radius(radius),
            "Concentrating",
        )
    ]

    assert positions["top_left"] == (113.86, 213.86)
    assert positions["bottom_right"] == (158.14, 258.14)
    assert positions["bottom_left"] == (107.68, 264.32)
    assert (
        status_marker_tooltip(
            hits,
            *positions["bottom_left"],
        )
        == "Concentrating"
    )
    assert status_marker_tooltip(hits, 136.0, 236.0) is None


def test_status_markers_do_not_overlap_target_allocation_badge() -> None:
    for cell_size in (40.0, 144.0):
        token_radius = max(14.0, int(cell_size * 0.38))
        center_x = center_y = cell_size / 2
        positions, marker_radius = status_marker_positions(
            cell_x=0.0,
            cell_y=0.0,
            center_x=center_x,
            center_y=center_y,
            token_radius=token_radius,
            cell_size=cell_size,
        )
        badge_x, badge_y = target_allocation_badge_position(
            center_x=center_x,
            center_y=center_y,
            token_radius=token_radius,
            top_right_reserved=True,
        )
        badge_radius = max(9.0, int(cell_size * 0.16))

        for marker_x, marker_y in positions.values():
            distance_squared = (badge_x - marker_x) ** 2 + (badge_y - marker_y) ** 2
            minimum_distance = badge_radius + marker_radius
            assert distance_squared > minimum_distance**2

        expected_unreserved_position = (
            center_x + token_radius * 0.72,
            center_y - token_radius * 0.72,
        )
        assert (
            target_allocation_badge_position(
                center_x=center_x,
                center_y=center_y,
                token_radius=token_radius,
                top_right_reserved=False,
            )
            == expected_unreserved_position
        )


def test_overlapping_marker_hit_prefers_last_painted_marker() -> None:
    hits = [
        StatusMarkerHit(10.0, 10.0, 8.0, "First"),
        StatusMarkerHit(10.0, 10.0, 8.0, "Last"),
    ]

    assert status_marker_tooltip(hits, 10.0, 10.0) == "Last"


def test_creature_name_label_expands_beyond_cell_and_stays_in_viewport() -> None:
    label_x, label_y, label_width, label_height = creature_name_label_rect(
        center_x=136.0,
        center_y=236.0,
        token_radius=27.0,
        cell_size=72.0,
        text_width=140.0,
        text_height=15.0,
        horizontal_padding=8.0,
        vertical_padding=6.0,
        viewport_width=300.0,
        viewport_height=300.0,
    )

    assert label_width == 156.0
    assert label_width > 72.0
    assert (label_x, label_y, label_height) == (58.0, 178.0, 27.0)

    edge_rect = creature_name_label_rect(
        center_x=12.0,
        center_y=12.0,
        token_radius=27.0,
        cell_size=72.0,
        text_width=400.0,
        viewport_width=220.0,
        viewport_height=160.0,
    )
    assert edge_rect == (3.0, 3.0, 214.0, 16.0)


def test_status_tooltip_label_stays_beside_marker_and_inside_viewport() -> None:
    assert status_tooltip_label_rect(
        anchor_x=50.0,
        anchor_y=60.0,
        text_width=100.0,
        text_height=30.0,
        horizontal_padding=8.0,
        vertical_padding=6.0,
        viewport_width=300.0,
        viewport_height=200.0,
    ) == (62.0, 72.0, 116.0, 42.0)
    assert status_tooltip_label_rect(
        anchor_x=295.0,
        anchor_y=195.0,
        text_width=100.0,
        text_height=30.0,
        horizontal_padding=8.0,
        vertical_padding=6.0,
        viewport_width=300.0,
        viewport_height=200.0,
    ) == (167.0, 141.0, 116.0, 42.0)
