"""System 1 game-bot loop: see, think, act."""

from __future__ import annotations

import os
import argparse
import time
from typing import Any

from vision import GameVision

try:
    from jev import Client
except ImportError as error:
    Client = None  # type: ignore[assignment,misc]
    _JEV_IMPORT_ERROR = error
else:
    _JEV_IMPORT_ERROR = None


ACTION_OPTIONS = ["JUMP", "DODGE_LEFT", "DODGE_RIGHT", "DO_NOTHING"]


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


class SimulatorClient:
    """Small local choice provider so --sim needs no network or API key."""

    def choice(self, _question: str, _options: list[str]) -> dict[str, Any]:
        distance = int(_question.rsplit(":", 1)[-1].split()[0])
        if distance <= 30:
            return {"choice": "JUMP", "probability": 0.950000}
        return {"choice": "DO_NOTHING", "probability": 0.875000}


def actuate(controller: Any, action: str, simulator_mode: bool) -> None:
    if simulator_mode:
        if action == "JUMP":
            print("[SIM HANDS] Pressing SPACE key...", flush=True)
        elif action == "DODGE_LEFT":
            print("[SIM HANDS] Pressing LEFT key...", flush=True)
        elif action == "DODGE_RIGHT":
            print("[SIM HANDS] Pressing RIGHT key...", flush=True)
        else:
            print("[SIM HANDS] No key press.", flush=True)
        return

    if controller is None:
        print(f"[HANDS FALLBACK] Could not press key for {action}.", flush=True)
        return

    from pynput import keyboard

    action_keys = {
        "JUMP": keyboard.Key.space,
        "DODGE_LEFT": keyboard.Key.left,
        "DODGE_RIGHT": keyboard.Key.right,
    }
    key = action_keys.get(action)
    if key is None:
        return
    try:
        controller.press(key)
        controller.release(key)
    except Exception as error:
        print(f"[HANDS FALLBACK] {error}", flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the System 1 game bot.")
    parser.add_argument(
        "--sim",
        action="store_true",
        help="run without display capture, Jev network access, or keyboard events",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    api_key = os.getenv("TYPESAFE_API_KEY")
    if args.sim:
        client = SimulatorClient()
        controller = None
    else:
        if not api_key:
            raise RuntimeError("TYPESAFE_API_KEY is required outside simulator mode.")
        if Client is None:
            raise RuntimeError(
                "The Jev SDK import failed. Install the Jev SDK that provides "
                "'jev.Client'; PyPI's typesafe-ai package is only a redirect shim."
            ) from _JEV_IMPORT_ERROR
        client = Client(api_key=api_key)
        try:
            from pynput import keyboard

            controller = keyboard.Controller()
        except Exception as error:
            print(f"[HANDS FALLBACK] Keyboard backend unavailable: {error}", flush=True)
            controller = None

    try:
        with GameVision(simulator_mode=args.sim) as vision:
            while True:
                start = time.time()
                vision.capture_and_process_frame()
                state = vision.get_serialized_state()
                action, probability = choose_action(client, state)
                actuate(controller, action, args.sim)
                latency_ms = (time.time() - start) * 1000
                print(
                    f"action={action} probability={probability:.6f} "
                    f"frame_latency_ms={latency_ms:.3f}",
                    flush=True,
                )
                elapsed = time.time() - start
                time.sleep(max(0.0, 0.1 - elapsed))
    except KeyboardInterrupt:
        print("Stopping game bot.")


if __name__ == "__main__":
    main()