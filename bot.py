"""System 1 game-bot loop: see, think, act."""

from __future__ import annotations

import os
import argparse
import signal
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from queue import Empty, Queue

from decision import DecisionProvider, SimulatorDecisionProvider, TypeSafeDecisionProvider
from decision import Decision
from input import InputController, NullController, PynputController, SimulatorController
from profiles import GameProfile, load_profile
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


class ActionLimiter:
    def __init__(self, min_interval: float, cooldown: float) -> None:
        self._min_interval = min_interval
        self._cooldown = cooldown
        self._last_action = ""
        self._last_action_at = 0.0

    def allows(self, action: str) -> bool:
        if action == "DO_NOTHING":
            return True
        now = time.monotonic()
        elapsed = now - self._last_action_at
        if elapsed < self._min_interval:
            return False
        if action == self._last_action and elapsed < self._cooldown:
            return False
        self._last_action = action
        self._last_action_at = now
        return True


def require_native_display() -> None:
    if os.name == "posix" and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        raise RuntimeError(
            "Native mode needs an X11 or Wayland display. Use --sim in a headless terminal."
        )


def create_keyboard_controller() -> object:
    try:
        from pynput import keyboard

        return keyboard.Controller()
    except Exception as error:
        raise RuntimeError(
            "Native keyboard input is unavailable. Check display and input permissions."
        ) from error


def run_native_preflight(profile: GameProfile, check_keyboard: bool) -> None:
    require_native_display()
    try:
        import cv2
        import mss
    except Exception as error:
        raise RuntimeError(
            "Native preflight needs opencv-python-headless and mss installed."
        ) from error

    with mss.mss() as capture:
        monitors = capture.monitors
        monitor = profile.monitor or monitors[1]
        capture.grab(monitor)
    print(f"[PREFLIGHT] display=ok monitors={len(monitors) - 1}", flush=True)
    print(f"[PREFLIGHT] opencv={cv2.__version__} capture=ok", flush=True)

    if check_keyboard:
        try:
            from pynput import keyboard

            keyboard.Controller()
        except Exception as error:
            raise RuntimeError(
                "Native keyboard preflight failed; use --observe-only or fix permissions."
            ) from error
        print("[PREFLIGHT] keyboard=ok", flush=True)
    else:
        print("[PREFLIGHT] keyboard=skipped", flush=True)


def install_emergency_signals(stop: threading.Event) -> None:
    def handle_signal(signum: int, _frame: object) -> None:
        print(f"[EMERGENCY STOP] signal={signum}", flush=True)
        stop.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


def stop_file_loop(path: str | None, stop: threading.Event) -> None:
    if not path:
        return
    while not stop.wait(0.1):
        if os.path.exists(path):
            print(f"[EMERGENCY STOP] stop file detected: {path}", flush=True)
            stop.set()
            return


def capture_loop(
    vision: GameVision,
    states: LatestStateQueue,
    stop: threading.Event,
    capture_hz: float,
) -> None:
    period = 1.0 / capture_hz
    while not stop.is_set():
        started_at = time.perf_counter()
        try:
            vision.capture_and_process_frame()
            states.put_latest(
                StateSnapshot(
                    state=vision.get_serialized_state(),
                    started_at=started_at,
                    captured_at=time.perf_counter(),
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
    profile: GameProfile,
    min_confidence: float,
    limiter: ActionLimiter,
) -> None:
    period = 1.0 / decision_hz
    pending: Future[Decision] | None = None
    pending_started = 0.0

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="system1-decision") as executor:
        while not stop.is_set():
            cycle_started = time.perf_counter()
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
                if time.perf_counter() - pending_started >= decision_timeout:
                    fallback_reason = "decision_timeout"
                else:
                    fallback_reason = "decision_in_flight"
            else:
                pending = executor.submit(provider.decide, snapshot.state)
                pending_started = time.perf_counter()
                try:
                    decision = pending.result(timeout=min(decision_timeout, period))
                    pending = None
                except TimeoutError:
                    fallback_reason = "decision_timeout"
                except Exception as error:
                    pending = None
                    fallback_reason = getattr(error, "category", type(error).__name__)

            if decision is None:
                decision = fallback_decision(fallback_reason)
            elif decision.confidence < min_confidence:
                fallback_reason = "low_confidence"
                decision = fallback_decision(fallback_reason)

            action_sent = actuate(
                controller,
                decision.action,
                simulator_mode,
                profile,
                limiter,
                stop,
            )
            engine_latency_ms = (time.perf_counter() - snapshot.started_at) * 1000
            state_age_ms = (time.perf_counter() - snapshot.captured_at) * 1000
            print(
                f"action={decision.action} confidence={decision.confidence:.6f} "
                f"probabilities={decision.probabilities} "
                f"engine_latency_ms={engine_latency_ms:.3f} "
                f"state_age_ms={state_age_ms:.3f} "
                f"action_sent={str(action_sent).lower()} "
                f"fallback={fallback_reason or 'none'}",
                flush=True,
            )
            stop.wait(max(0.0, period - (time.perf_counter() - cycle_started)))


def actuate(
    controller: InputController,
    action: str,
    simulator_mode: bool,
    profile: GameProfile,
    limiter: ActionLimiter,
    stop: threading.Event,
) -> bool:
    if stop.is_set():
        return False
    if not limiter.allows(action):
        print(f"[HANDS SAFETY] Cooldown blocked {action}.", flush=True)
        return False
    try:
        return controller.press(action)
    except Exception as error:
        print(f"[HANDS FALLBACK] {error}", flush=True)
        stop.set()
        return False


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
    parser.add_argument("--action-cooldown", type=float, default=0.15)
    parser.add_argument("--min-action-interval", type=float, default=0.05)
    parser.add_argument("--stop-file", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--observe-only", action="store_true")
    parser.add_argument("--min-confidence", type=float, default=None)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="check native display/capture/input prerequisites and exit",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    profile = load_profile(args.profile)
    min_confidence = (
        profile.min_confidence if args.min_confidence is None else args.min_confidence
    )
    if any(
        value <= 0
        for value in (
            args.capture_hz,
            args.decision_hz,
            args.decision_timeout,
            args.action_cooldown,
            args.min_action_interval,
        )
    ):
        raise ValueError("All rates, cooldowns, and timeouts must be positive.")
    if not 0 <= min_confidence <= 1:
        raise ValueError("Minimum confidence must be in [0, 1].")
    if args.preflight:
        run_native_preflight(profile, check_keyboard=not args.observe_only)
        return
    api_key = os.getenv("TYPESAFE_API_KEY")
    if args.observe_only:
        provider = SimulatorDecisionProvider() if args.sim else None
        if provider is None:
            if not api_key:
                raise RuntimeError("TYPESAFE_API_KEY is required outside simulator mode.")
            require_native_display()
            provider = TypeSafeDecisionProvider(
                api_key=api_key,
                model=args.model or profile.model,
            )
        controller: InputController = NullController()
    elif args.sim:
        provider: DecisionProvider = SimulatorDecisionProvider()
        controller: InputController = SimulatorController(profile)
    else:
        require_native_display()
        if not api_key:
            raise RuntimeError("TYPESAFE_API_KEY is required outside simulator mode.")
        provider = TypeSafeDecisionProvider(
            api_key=api_key,
            model=args.model or profile.model,
        )
        controller = NullController() if args.observe_only else PynputController(profile)

    stop = threading.Event()
    install_emergency_signals(stop)
    limiter = ActionLimiter(args.min_action_interval, args.action_cooldown)
    states = LatestStateQueue()
    stop_file_thread = threading.Thread(
        target=stop_file_loop,
        args=(args.stop_file, stop),
        name="system1-emergency-stop",
        daemon=True,
    )
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
                    profile,
                    min_confidence,
                    limiter,
                ),
                name="system1-decision-loop",
                daemon=True,
            )
            stop_file_thread.start()
            capture_thread.start()
            decision_thread.start()
            while (
                capture_thread.is_alive()
                and decision_thread.is_alive()
                and not stop.is_set()
            ):
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("Stopping game bot.")
    finally:
        stop.set()
        if "capture_thread" in locals():
            capture_thread.join(timeout=0.5)
        if "decision_thread" in locals():
            decision_thread.join(timeout=0.5)
        close = getattr(provider, "close", None)
        if callable(close):
            close()
        controller.release_all()


if __name__ == "__main__":
    main()