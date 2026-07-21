from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT.parent
REPO_ROOT = SRC_ROOT.parent
CONTENT_ROOT = REPO_ROOT / "content"
SCENARIOS_ROOT = CONTENT_ROOT / "scenarios"
SYSTEM_CONTENT_ROOT = CONTENT_ROOT / "system"
