from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
CONTENT_ROOT = APP_ROOT / "content"
SCENARIOS_ROOT = CONTENT_ROOT / "scenarios"
SYSTEM_CONTENT_ROOT = CONTENT_ROOT / "system"
