"""Small, JSON-friendly game profile definitions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_ACTIONS = {
    "JUMP": "space",
    "DODGE_LEFT": "left",
    "DODGE_RIGHT": "right",
    "DO_NOTHING": "none",
}
DEFAULT_DETECTOR_CONFIG = {
    "hsv_lower": [35, 90, 140],
    "hsv_upper": [90, 255, 255],
    "min_area": 12,
    "roi_top_fraction": 0.333,
}


@dataclass(frozen=True)
class GameProfile:
    name: str = "default"
    monitor: dict[str, int] | None = None
    actions: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ACTIONS))
    detector: str = "green_obstacle"
    detector_config: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_DETECTOR_CONFIG)
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameProfile":
        monitor = data.get("monitor")
        if monitor is not None:
            required = {"left", "top", "width", "height"}
            if set(monitor) != required:
                raise ValueError("Profile monitor must contain left, top, width, height.")
            monitor = {key: int(value) for key, value in monitor.items()}

        actions = dict(DEFAULT_ACTIONS)
        actions.update(
            {str(key): str(value) for key, value in data.get("actions", {}).items()}
        )
        if set(actions) != set(DEFAULT_ACTIONS):
            raise ValueError("Profile actions must match the supported action set.")

        detector_config = dict(DEFAULT_DETECTOR_CONFIG)
        detector_config.update(data.get("detector_config", {}))
        return cls(
            name=str(data.get("name", "custom")),
            monitor=monitor,
            actions=actions,
            detector=str(data.get("detector", "green_obstacle")),
            detector_config=detector_config,
        )


def load_profile(path: str | None) -> GameProfile:
    if path is None:
        return GameProfile()
    with Path(path).open("r", encoding="utf-8") as profile_file:
        data = json.load(profile_file)
    if not isinstance(data, dict):
        raise ValueError("Profile JSON must contain an object at the top level.")
    return GameProfile.from_dict(data)