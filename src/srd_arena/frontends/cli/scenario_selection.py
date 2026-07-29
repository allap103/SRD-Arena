from pathlib import Path

from ...content.paths import SCENARIOS_ROOT
from ...content.scenarios import list_scenarios


def select_scenario_directory(root: Path = SCENARIOS_ROOT) -> Path:
    """Prompt a CLI user to select one of the available scenarios."""
    scenarios = list_scenarios(root)
    if not scenarios:
        raise FileNotFoundError("No scenarios are available in content/scenarios/.")
    print("Available scenarios:")
    for index, scenario in enumerate(scenarios, start=1):
        print(f"{index}. {scenario.label}")
    while True:
        choice = input("Choose a scenario: ")
        try:
            selected_index = int(choice) - 1
        except ValueError:
            print("Please enter a valid number.")
            continue
        if 0 <= selected_index < len(scenarios):
            return scenarios[selected_index].directory
        print("Please choose one of the listed scenarios.")
