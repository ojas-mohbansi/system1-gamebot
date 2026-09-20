"""Low-latency screen capture and compact game-state extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VisionState:
    threat_distance: int
    lane_position: float
    speed: float
    threat_visible: bool


class GameVision:
    """Capture one configured screen region and extract simple pixel telemetry."""

    def __init__(
        self,
        monitor: dict[str, int] | None = None,
        simulator_mode: bool = False,
    ) -> None:
        self.simulator_mode = simulator_mode
        self._sct: Any = None
        self._cv2: Any = None
        self._np: Any = None
        self._monitor = monitor or {}
        self._simulated_distance = 100
        if not simulator_mode:
            import cv2
            import mss
            import numpy as np

            self._cv2 = cv2
            self._np = np
            self._sct = mss.mss()
            self._monitor = monitor or dict(self._sct.monitors[1])
        self._previous_threat_distance: int | None = None
        self._state = VisionState(0, 0.5, 0.0, False)

    @property
    def monitor(self) -> dict[str, int]:
        return self._monitor

    def capture_and_process_frame(self) -> Any:
        """Grab BGRA pixels and update the current obstacle telemetry."""
        if self.simulator_mode:
            return self._capture_simulated_frame()

        if self._sct is None:
            raise RuntimeError("Native screen capture is not initialized.")
        screenshot = self._sct.grab(self._monitor)
        frame = self._np.asarray(screenshot, dtype=self._np.uint8)[:, :, :3]
        self._update_state(frame)
        return frame

    def _capture_simulated_frame(self) -> bytearray:
        distance = self._simulated_distance
        frame = bytearray(180 * 320 * 3)
        for row in range(100, 130):
            for column in range(155, 165):
                pixel = (row * 320 + column) * 3
                frame[pixel : pixel + 3] = bytes((0, 220, 0))
        self._state = VisionState(
            threat_distance=distance,
            lane_position=0.5,
            speed=5.0,
            threat_visible=True,
        )
        self._simulated_distance -= 5
        if self._simulated_distance < 5:
            self._simulated_distance = 100
        return frame

    def _update_state(self, frame: Any) -> None:
        height, width = frame.shape[:2]
        hsv = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2HSV)

        # Yeh mask bright green obstacle/health-bar pixels ko isolate karta hai.
        mask = self._cv2.inRange(
            hsv,
            self._np.array((35, 90, 140), dtype=self._np.uint8),
            self._np.array((90, 255, 255), dtype=self._np.uint8),
        )
        mask[: height // 3, :] = 0
        contours, _ = self._cv2.findContours(
            mask,
            self._cv2.RETR_EXTERNAL,
            self._cv2.CHAIN_APPROX_SIMPLE,
        )

        candidates = [
            contour for contour in contours if self._cv2.contourArea(contour) >= 12
        ]
        if not candidates:
            self._state = VisionState(0, 0.5, 0.0, False)
            return

        obstacle = max(candidates, key=self._cv2.contourArea)
        x, _, obstacle_width, _ = self._cv2.boundingRect(obstacle)
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
        if self.simulator_mode:
            return f"Obstacle in Center lane, distance: {state.threat_distance} px"
        return (
            f"threat_distance={state.threat_distance};"
            f"lane_position={state.lane_position:.3f};"
            f"speed={state.speed:.3f};"
            f"threat_visible={str(state.threat_visible).lower()}"
        )

    def close(self) -> None:
        if self._sct is not None:
            self._sct.close()

    def __enter__(self) -> "GameVision":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()