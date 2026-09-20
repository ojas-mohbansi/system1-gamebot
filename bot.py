"""System 1 game-bot loop: see, think, act."""

from __future__ import annotations

import os
import argparse
import time

from decision import DecisionProvider, SimulatorDecisionProvider, TypeSafeDecisionProvider
from vision import GameVision

def actuate(controller: object, action: str, simulator_mode: bool) -> None:
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
        provider: DecisionProvider = SimulatorDecisionProvider()
        controller = None
    else:
        if not api_key:
            raise RuntimeError("TYPESAFE_API_KEY is required outside simulator mode.")
        provider = TypeSafeDecisionProvider(api_key=api_key)
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
                decision = provider.decide(state)
                actuate(controller, decision.action, args.sim)
                latency_ms = (time.time() - start) * 1000
                print(
                    f"action={decision.action} confidence={decision.confidence:.6f} "
                    f"probabilities={decision.probabilities} "
                    f"frame_latency_ms={latency_ms:.3f}",
                    flush=True,
                )
                elapsed = time.time() - start
                time.sleep(max(0.0, 0.1 - elapsed))
    except KeyboardInterrupt:
        print("Stopping game bot.")
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()