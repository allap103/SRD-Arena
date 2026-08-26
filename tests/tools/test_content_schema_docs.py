from pathlib import Path

from srd_arena.tools.content_schema_docs import generate_content_schema_docs


def test_generate_selected_schema_reference_without_diagram(tmp_path: Path) -> None:
    (tmp_path / "equipment.svg").write_text("stale", encoding="utf-8")
    generated = generate_content_schema_docs(
        tmp_path,
        selected_slugs={"equipment"},
        include_diagrams=False,
    )

    assert [document.slug for document in generated] == ["equipment"]
    assert (tmp_path / "equipment.json").is_file()
    assert (tmp_path / "equipment.html").is_file()

    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "equipment.html" in index
    assert "equipment.json" in index
    assert "equipment.svg" not in index


def test_generate_unknown_selection_as_empty_index(tmp_path: Path) -> None:
    generated = generate_content_schema_docs(
        tmp_path,
        selected_slugs={"unknown"},
        include_diagrams=False,
    )

    assert generated == []
    assert (tmp_path / "index.html").is_file()
