"""Low-latency screen capture and compact game-state extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import mss
import numpy as np


@dataclass(frozen=True)
class VisionState:
    threat_distance: int
    lane_position: float
    speed: float
    threat_visible: bool


class GameVision:
    """Capture one configured screen region and extract simple pixel telemetry."""

    def __init__(self, monitor: dict[str, int] | None = None) -> None:
        self._sct = mss.mss()
        self._monitor = monitor or dict(self._sct.monitors[1])
        self._previous_threat_distance: int | None = None
        self._state = VisionState(0, 0.5, 0.0, False)

    @property
    def monitor(self) -> dict[str, int]:
        return self._monitor

    def capture_and_process_frame(self) -> np.ndarray:
        """Grab BGRA pixels and update the current obstacle telemetry."""
        screenshot = self._sct.grab(self._monitor)
        frame = np.asarray(screenshot, dtype=np.uint8)[:, :, :3]
        self._update_state(frame)
        return frame

    def _update_state(self, frame: np.ndarray) -> None:
        height, width = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Yeh mask bright green obstacle/health-bar pixels ko isolate karta hai.
        mask = cv2.inRange(
            hsv,
            np.array((35, 90, 140), dtype=np.uint8),
            np.array((90, 255, 255), dtype=np.uint8),
        )
        mask[: height // 3, :] = 0
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = [contour for contour in contours if cv2.contourArea(contour) >= 12]
        if not candidates:
            self._state = VisionState(0, 0.5, 0.0, False)
            return

        obstacle = max(candidates, key=cv2.contourArea)
        x, _, obstacle_width, _ = cv2.boundingRect(obstacle)
        center_x = x + obstacle_width / 2
        threat_distance = max(width - int(center_x), 0)
        lane_position = round(float(center_x / max(width, 1)), 3)

        previous = self._previous_threat_distance
        speed = 0.0 if previous is None else round(float(previous - threat_distance), 3)
        self._previous_threat_distance = threat_distance
        self._state = VisionState(
            threat_distance=threat_distance,
            lane_position=lane_position,
            speed=speed,
            threat_visible=True,
        )

    def get_serialized_state(self) -> str:
        """Return a compact, stable text representation for the decision model."""
        state = self._state
        return (
            f"threat_distance={state.threat_distance};"
            f"lane_position={state.lane_position:.3f};"
            f"speed={state.speed:.3f};"
            f"threat_visible={str(state.threat_visible).lower()}"
        )

    def close(self) -> None:
        self._sct.close()

    def __enter__(self) -> "GameVision":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()