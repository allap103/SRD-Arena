from pathlib import Path

from fastapi.testclient import TestClient

from game.api.savegames import SavegameApi
from game.engine import Game
from game.save import SAVEGAME_EXAMPLE, create_save

FIXTURE_GAME_DIR = Path(__file__).parent / "fixtures" / "graph_game"


def test_get_save_returns_current_session_state() -> None:
    api = SavegameApi(Game(str(FIXTURE_GAME_DIR), start_scene="start"))
    api.session.current_scene_id = "shared_target"
    client = TestClient(api.create_app())

    response = client.get("/save")

    assert response.status_code == 200
    assert response.json()["current_scene_id"] == "shared_target"
    assert response.json()["start_scene_id"] == "start"


def test_post_load_restores_session_from_payload() -> None:
    source_api = SavegameApi(Game(str(FIXTURE_GAME_DIR), start_scene="start"))
    source_api.session.current_scene_id = "shared_target"
    source_api.session.player.take_damage(4)
    payload = create_save(source_api.session).model_dump(mode="json")

    target_api = SavegameApi(Game(str(FIXTURE_GAME_DIR), start_scene="start"))
    client = TestClient(target_api.create_app())

    response = client.post("/load", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert target_api.session.current_scene_id == "shared_target"
    assert target_api.session.player.get_health() == 8


def test_openapi_exposes_working_load_example() -> None:
    api = SavegameApi(Game("sample_game"))
    client = TestClient(api.create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    example = response.json()["components"]["schemas"]["SaveGame"]["example"]
    assert example == SAVEGAME_EXAMPLE


def test_get_stats_returns_selected_application_stats() -> None:
    api = SavegameApi(Game(str(FIXTURE_GAME_DIR), start_scene="start"))
    client = TestClient(api.create_app())

    stats_response = client.get("/stats")

    assert stats_response.status_code == 200
    assert stats_response.json()["current_scene_id"] == "start"
    assert stats_response.json()["scene_count"] == 2
    assert stats_response.json()["player_health"] == 12
    assert stats_response.json()["player_max_health"] == 12
    assert stats_response.json()["has_active_encounter"] is False


def test_get_actions_returns_available_choices_for_current_scene() -> None:
    api = SavegameApi(Game(str(FIXTURE_GAME_DIR), start_scene="start"))
    client = TestClient(api.create_app())

    response = client.get("/actions")

    assert response.status_code == 200
    assert response.json()["current_scene_id"] == "start"
    assert response.json()["actions"] == [
        {"index": 0, "label": "Take the bright path."},
        {"index": 1, "label": "Take the quiet path."},
        {"index": 2, "label": "Open the missing door."},
        {"index": 3, "label": "Save game"},
        {"index": 4, "label": "Load game"},
        {"index": 5, "label": "Exit game"},
    ]


def test_get_actions_returns_encounter_actions_for_encounter_scene() -> None:
    api = SavegameApi(Game("sample_game"))
    api.session.current_scene_id = "test_encounter"
    client = TestClient(api.create_app())

    response = client.get("/actions")

    assert response.status_code == 200
    assert response.json()["current_scene_id"] == "test_encounter"
    labels = [option["label"] for option in response.json()["actions"]]
    assert "Move up" in labels
    assert "Wait" in labels
    assert "Flee encounter" in labels
    assert "Save game" in labels


def test_post_action_advances_game_state() -> None:
    api = SavegameApi(Game(str(FIXTURE_GAME_DIR), start_scene="start"))
    client = TestClient(api.create_app())

    response = client.post("/actions/0")

    assert response.status_code == 200
    assert response.json()["selected_index"] == 0
    assert response.json()["selected_action"] == "Take the bright path."
    assert response.json()["current_scene_id"] == "shared_target"
    assert response.json()["scene_changed"] is True
    assert api.session.current_scene_id == "shared_target"


def test_post_action_rejects_invalid_index() -> None:
    api = SavegameApi(Game(str(FIXTURE_GAME_DIR), start_scene="start"))
    client = TestClient(api.create_app())

    response = client.post("/actions/999")

    assert response.status_code == 400
    assert "out of range" in response.json()["detail"]
