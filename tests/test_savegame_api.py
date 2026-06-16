from pathlib import Path

from fastapi.testclient import TestClient

from game.api.savegames import SavegameApi
from game.engine import Game
from game.save import create_save

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
