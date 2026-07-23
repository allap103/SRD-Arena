from ..sources import SOURCE_PRIORITY, load_json as _load_json


def _slug(value: str) -> str:
    return value.lower().replace("'", "").replace(",", "").replace(" ", "_")
