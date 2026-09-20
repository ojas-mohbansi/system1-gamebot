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
SUPPORTED_DETECTORS = {"green_obstacle"}
SUPPORTED_SPECIAL_KEYS = {"space", "left", "right", "up", "down", "enter", "esc", "none"}


@dataclass(frozen=True)
class GameProfile:
    name: str = "default"
    model: str = "jev-latest"
    min_confidence: float = 0.0
    monitor: dict[str, int] | None = None
    actions: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ACTIONS))
    detector: str = "green_obstacle"
    detector_config: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_DETECTOR_CONFIG)
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameProfile":
        detector = str(data.get("detector", "green_obstacle"))
        if detector not in SUPPORTED_DETECTORS:
            raise ValueError(f"Unsupported detector: {detector}")

        monitor = data.get("monitor")
        if monitor is not None:
            required = {"left", "top", "width", "height"}
            if not isinstance(monitor, dict) or set(monitor) != required:
                raise ValueError("Profile monitor must contain left, top, width, height.")
            monitor = {key: int(value) for key, value in monitor.items()}
            if monitor["width"] <= 0 or monitor["height"] <= 0:
                raise ValueError("Profile monitor width and height must be positive.")

        actions = dict(DEFAULT_ACTIONS)
        actions.update(
            {str(key): str(value) for key, value in data.get("actions", {}).items()}
        )
        if set(actions) != set(DEFAULT_ACTIONS):
            raise ValueError("Profile actions must match the supported action set.")
        for action, key in actions.items():
            if key not in SUPPORTED_SPECIAL_KEYS and len(key) != 1:
                raise ValueError(f"Unsupported key mapping for {action}: {key}")

        detector_config = dict(DEFAULT_DETECTOR_CONFIG)
        detector_config.update(data.get("detector_config", {}))
        hsv_lower = detector_config["hsv_lower"]
        hsv_upper = detector_config["hsv_upper"]
        if (
            not isinstance(hsv_lower, list)
            or not isinstance(hsv_upper, list)
            or len(hsv_lower) != 3
            or len(hsv_upper) != 3
            or any(not 0 <= value <= 255 for value in hsv_lower + hsv_upper)
        ):
            raise ValueError("HSV bounds must be three integers from 0 to 255.")
        if float(detector_config["min_area"]) <= 0:
            raise ValueError("Detector min_area must be positive.")
        if not 0 <= float(detector_config["roi_top_fraction"]) < 1:
            raise ValueError("Detector roi_top_fraction must be in [0, 1).")
        min_confidence = float(data.get("min_confidence", 0.0))
        if not 0 <= min_confidence <= 1:
            raise ValueError("Profile min_confidence must be in [0, 1].")
        return cls(
            name=str(data.get("name", "custom")),
            model=str(data.get("model", "jev-latest")),
            min_confidence=min_confidence,
            monitor=monitor,
            actions=actions,
            detector=detector,
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