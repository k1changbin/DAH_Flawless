"""Remove scorer-only truth before state reaches Blue."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from dah_flawless.observation import attach_red_visibility_policy


def redact_state(state: dict) -> dict:
    blue_observed = deepcopy(state["blue_observed"])
    attach_red_visibility_policy(blue_observed)
    redacted = {
        "round": state["round"],
        "seed": state["seed"],
        "blue_observed": blue_observed,
        "mission": deepcopy(state["mission"]),
        "capabilities": deepcopy(state["capabilities"]),
        "defense_runtime": deepcopy(state["defense_runtime"]),
    }
    assert_no_world(redacted)
    return redacted


def assert_no_world(value: Any) -> None:
    if isinstance(value, dict):
        if "world" in value:
            raise AssertionError('redacted state leaked scorer truth key "world"')
        for nested in value.values():
            assert_no_world(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_world(nested)
