"""System 1 game-bot loop: see, think, act."""

from __future__ import annotations

import os
import time
from typing import Any

from pynput import keyboard

from vision import GameVision

try:
    from jev import Client
except ImportError as error:
    Client = None  # type: ignore[assignment,misc]
    _JEV_IMPORT_ERROR = error
else:
    _JEV_IMPORT_ERROR = None


ACTION_OPTIONS = ["JUMP", "DODGE_LEFT", "DODGE_RIGHT", "DO_NOTHING"]
ACTION_KEYS = {
    "JUMP": keyboard.Key.space,
    "DODGE_LEFT": keyboard.Key.left,
    "DODGE_RIGHT": keyboard.Key.right,
}


def _response_value(response: Any, name: str, default: Any) -> Any:
    if isinstance(response, dict):
        return response.get(name, default)
    return getattr(response, name, default)


def choose_action(client: Any, state: str) -> tuple[str, float]:
    question = (
        "Given this live game state, choose exactly one action that maximizes survival: "
        f"{state}"
    )
    response = client.choice(question, ACTION_OPTIONS)
    action = str(_response_value(response, "choice", response)).upper().strip()
    probability = float(
        _response_value(
            response,
            "probability",
            _response_value(response, "confidence", 0.0),
        )
    )
    if action not in ACTION_OPTIONS:
        action = "DO_NOTHING"
    return action, probability


def actuate(controller: keyboard.Controller, action: str) -> None:
    key = ACTION_KEYS.get(action)
    if key is None:
        return
    controller.press(key)
    controller.release(key)


def main() -> None:
    api_key = os.getenv("TYPESAFE_API_KEY")
    if not api_key:
        raise RuntimeError("TYPESAFE_API_KEY is required in the environment.")
    if Client is None:
        raise RuntimeError(
            "The Jev SDK import failed. Install the Jev SDK that provides "
            "'jev.Client'; PyPI's typesafe-ai package is only a redirect shim."
        ) from _JEV_IMPORT_ERROR

    client = Client(api_key=api_key)
    controller = keyboard.Controller()

    try:
        with GameVision() as vision:
            while True:
                start = time.time()
                vision.capture_and_process_frame()
                state = vision.get_serialized_state()
                action, probability = choose_action(client, state)
                actuate(controller, action)
                latency_ms = (time.time() - start) * 1000
                print(
                    f"action={action} probability={probability:.6f} "
                    f"frame_latency_ms={latency_ms:.3f}",
                    flush=True,
                )
    except KeyboardInterrupt:
        print("Stopping game bot.")


if __name__ == "__main__":
    main()