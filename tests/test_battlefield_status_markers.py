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
from srd_arena.frontends.shared.session import (
    BattlefieldCreatureView,
    GridPositionView,
    _build_battlefield_view,
    _effective_condition_names,
)


def _creature(
    creature_id: str,
    team_id: str,
    *,
    conditions: list[str] | None = None,
    effective_conditions: list[str] | None = None,
) -> dict[str, object]:
    return {
        "creature_id": creature_id,
        "name": creature_id.replace("_", " ").title(),
        "label": creature_id,
        "token_image": None,
        "team_id": team_id,
        "position": {"x": 0, "y": 0},
        "health": 10,
        "max_health": 10,
        "conditions": list(conditions or ()),
        "effective_conditions": [
            {"condition": condition, "provider_ids": []}
            for condition in effective_conditions or ()
        ],
        "is_alive": True,
    }


def test_battlefield_view_groups_concentration_buffs_debuffs_and_conditions() -> None:
    combat_state = {
        "grid": {"width": 4, "height": 4},
        "round_number": 1,
        "decision": {"creature_ref": "caster", "kind": "turn"},
        "creatures": {
            "caster": _creature("caster", "heroes"),
            "ally": _creature(
                "ally",
                "heroes",
                conditions=["paralyzed"],
                effective_conditions=[
                    "paralyzed",
                    "incapacitated",
                    "incapacitated",
                ],
            ),
            "enemy": _creature("enemy", "monsters"),
        },
        "ongoing_effects": [
            {
                "kind": "concentration",
                "polarity": "beneficial",
                "source": {
                    "applied_by_ref": "caster",
                    "definition_id": "bless",
                },
                "target_refs": ["ally"],
                "parameters": {"effect_label": "Bless"},
            },
            {
                "kind": "concentration",
                "polarity": "harmful",
                "source": {
                    "applied_by_ref": "enemy",
                    "definition_id": "slow",
                },
                "target_refs": ["ally"],
                "parameters": {"effect_label": "Slow"},
            },
            {
                "kind": "spell",
                "polarity": "beneficial",
                "source": {
                    "applied_by_ref": "caster",
                    "definition_id": "bless",
                },
                "target_refs": ["ally"],
                "parameters": {"effect_label": "Bless"},
            },
            {
                "kind": "spell",
                "polarity": "beneficial",
                "source": {
                    "definition_id": "magic_zone",
                },
                "target_refs": ["ally"],
                "parameters": {"effect_label": "Magic Zone"},
            },
            {
                "kind": "spell",
                "polarity": "neutral",
                "source": {
                    "applied_by_ref": "caster",
                    "definition_id": "ambiguous_effect",
                },
                "target_refs": ["ally"],
                "parameters": {"effect_label": "Ambiguous Effect"},
            },
        ],
    }

    battlefield = _build_battlefield_view(
        combat_state,
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
    suppressed = _creature(
        "target",
        "heroes",
        conditions=["prone"],
        effective_conditions=[],
    )
    fallback = _creature("target", "heroes", conditions=["prone"])
    fallback.pop("effective_conditions")

    assert _effective_condition_names(suppressed) == ()
    assert _effective_condition_names(fallback) == ("prone",)


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
