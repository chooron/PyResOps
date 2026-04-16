from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).parent / "config" / "scenarios_config.yaml"


@lru_cache(maxsize=1)
def load_scenarios_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    scenarios = raw.get("scenarios", {})
    dynamic_triggers = raw.get("dynamic_triggers", {})
    automated_config = raw.get("automated_config", {})

    normalized_scenarios: dict[str, dict] = {}
    for scenario_id, scenario in scenarios.items():
        merged = dict(scenario or {})
        merged.setdefault("id", scenario_id)
        normalized_scenarios[scenario_id] = merged

    return {
        "scenarios": normalized_scenarios,
        "dynamic_triggers": dynamic_triggers,
        "automated_config": automated_config,
    }


def get_scenarios() -> dict[str, dict]:
    return copy.deepcopy(load_scenarios_config()["scenarios"])


def get_scenario(scenario_id: str) -> dict:
    return get_scenarios()[scenario_id]


def get_dynamic_triggers() -> dict[str, list[dict]]:
    return copy.deepcopy(load_scenarios_config()["dynamic_triggers"])


def get_automated_scenarios() -> dict[str, dict]:
    scenarios = get_scenarios()
    automated = copy.deepcopy(load_scenarios_config()["automated_config"])
    merged: dict[str, dict] = {}
    for scenario_id, config in automated.items():
        scenario = scenarios[scenario_id].copy()
        scenario.update(config or {})
        scenario["id"] = scenario_id
        merged[scenario_id] = scenario
    return merged


def get_deviation_scenarios(scenario_id: str) -> list[dict]:
    automated = get_automated_scenarios()
    scenario = automated.get(scenario_id, {})
    return copy.deepcopy(scenario.get("deviation_scenarios", []))


def clear_scenarios_config_cache() -> None:
    load_scenarios_config.cache_clear()
