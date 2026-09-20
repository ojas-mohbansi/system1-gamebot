"""System 1 game-bot loop: see, think, act."""

from __future__ import annotations

import os
import argparse
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from queue import Empty, Queue

from decision import DecisionProvider, SimulatorDecisionProvider, TypeSafeDecisionProvider
from decision import Decision
from vision import GameVision


@dataclass(frozen=True)
class StateSnapshot:
    state: str
    started_at: float
    captured_at: float


class LatestStateQueue:
    """One-slot handoff so stale states never build up in memory."""

    def __init__(self) -> None:
        self._queue: Queue[StateSnapshot] = Queue(maxsize=1)

    def put_latest(self, snapshot: StateSnapshot) -> None:
        try:
            self._queue.get_nowait()
        except Empty:
            pass
        try:
            self._queue.put_nowait(snapshot)
        except Exception:
            pass

    def get(self, timeout: float) -> StateSnapshot:
        return self._queue.get(timeout=timeout)


def capture_loop(
    vision: GameVision,
    states: LatestStateQueue,
    stop: threading.Event,
    capture_hz: float,
) -> None:
    period = 1.0 / capture_hz
    while not stop.is_set():
        started_at = time.time()
        try:
            vision.capture_and_process_frame()
            states.put_latest(
                StateSnapshot(
                    state=vision.get_serialized_state(),
                    started_at=started_at,
                    captured_at=time.time(),
                )
            )
        except Exception as error:
            print(f"[EYES FALLBACK] Capture stopped: {error}", flush=True)
            stop.set()
            return
        stop.wait(max(0.0, period - (time.time() - started_at)))


def fallback_decision(reason: str) -> Decision:
    return Decision("DO_NOTHING", 0.0, {"DO_NOTHING": 1.0})


def decision_loop(
    provider: DecisionProvider,
    controller: object,
    states: LatestStateQueue,
    stop: threading.Event,
    simulator_mode: bool,
    decision_hz: float,
    decision_timeout: float,
) -> None:
    period = 1.0 / decision_hz
    pending: Future[Decision] | None = None
    pending_started = 0.0

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="system1-decision") as executor:
        while not stop.is_set():
            cycle_started = time.time()
            try:
                snapshot = states.get(timeout=period)
            except Empty:
                continue

            fallback_reason = ""
            decision: Decision | None = None
            if pending is not None and pending.done():
                try:
                    pending.result()
                except Exception:
                    pass
                pending = None

            if pending is not None:
                if time.time() - pending_started >= decision_timeout:
                    fallback_reason = "decision_timeout"
                else:
                    fallback_reason = "decision_in_flight"
            else:
                pending = executor.submit(provider.decide, snapshot.state)
                pending_started = time.time()
                try:
                    decision = pending.result(timeout=min(decision_timeout, period))
                    pending = None
                except TimeoutError:
                    fallback_reason = "decision_timeout"
                except Exception as error:
                    pending = None
                    fallback_reason = type(error).__name__

            if decision is None:
                decision = fallback_decision(fallback_reason)

            actuate(controller, decision.action, simulator_mode)
            engine_latency_ms = (time.time() - snapshot.started_at) * 1000
            state_age_ms = (time.time() - snapshot.captured_at) * 1000
            print(
                f"action={decision.action} confidence={decision.confidence:.6f} "
                f"probabilities={decision.probabilities} "
                f"engine_latency_ms={engine_latency_ms:.3f} "
                f"state_age_ms={state_age_ms:.3f} "
                f"fallback={fallback_reason or 'none'}",
                flush=True,
            )
            stop.wait(max(0.0, period - (time.time() - cycle_started)))


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
    parser.add_argument("--capture-hz", type=float, default=100.0)
    parser.add_argument("--decision-hz", type=float, default=10.0)
    parser.add_argument("--decision-timeout", type=float, default=0.2)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.capture_hz <= 0 or args.decision_hz <= 0 or args.decision_timeout <= 0:
        raise ValueError("Capture rate, decision rate, and timeout must be positive.")
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

    stop = threading.Event()
    states = LatestStateQueue()
    try:
        with GameVision(simulator_mode=args.sim) as vision:
            capture_thread = threading.Thread(
                target=capture_loop,
                args=(vision, states, stop, args.capture_hz),
                name="system1-capture",
                daemon=True,
            )
            decision_thread = threading.Thread(
                target=decision_loop,
                args=(
                    provider,
                    controller,
                    states,
                    stop,
                    args.sim,
                    args.decision_hz,
                    args.decision_timeout,
                ),
                name="system1-decision-loop",
                daemon=True,
            )
            capture_thread.start()
            decision_thread.start()
            while capture_thread.is_alive() and decision_thread.is_alive():
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("Stopping game bot.")
    finally:
        stop.set()
        close = getattr(provider, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()