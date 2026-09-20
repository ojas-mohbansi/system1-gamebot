# system1-gamebot

`system1-gamebot` is a small Python framework for experimenting with screen-driven game automation.

It follows a simple loop:

```text
capture -> detect -> ask TypeSafe/Jev -> apply safety rules -> act
```

The project is designed to be easy to test in a headless GitHub Codespace before moving native input and screen capture to a real machine.

## What works today

- Headless simulator mode with a moving obstacle
- TypeSafe System One `Choice` integration through `TypeSafeClient.system_one()`
- Native `mss` capture and OpenCV detector scaffolding
- Simulator, observation-only, and `pynput` input controllers
- Profile-based monitor, detector, HSV, model, confidence, and key settings
- Bounded latest-state handoff between capture and decision loops
- Confidence gating, action cooldowns, emergency stop, and shutdown cleanup
- Human-readable and JSON Lines telemetry
- Dependency-free unit tests for the core behavior

This is a reusable framework, not a plug-and-play bot for every game. Each game still needs a profile and usually a detector calibrated for its visuals.

## Quick Start: Codespaces

The simulator is the right first run in a browser terminal. It does not need a display, keyboard permissions, an API key, OpenCV, `mss`, or `pynput`.

```bash
python -m venv .venv
source .venv/bin/activate
python bot.py --sim
```

You should see simulated actions, confidence values, latency, fallback information, and a final runtime summary when the process stops.

Inspect decisions without simulated or native input:

```bash
python bot.py --sim --observe-only
```

Use structured telemetry for scripts and benchmarks:

```bash
python bot.py --sim --jsonl
```

Stop the process with `Ctrl+C`.

## Install Native Dependencies

Native mode requires a real graphical session and input permissions. Create an environment and install the pinned packages:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export TYPESAFE_API_KEY="your-api-key"
```

The current requirements include:

- `mss` for screen capture
- `opencv-python-headless` for pixel processing
- `pynput` for keyboard events
- `typesafe-sdk` for TypeSafe System One

The public TypeSafe Python API is `TypeSafeClient.system_one()` plus the `Choice` primitive. Jev is TypeSafe's flagship System One model, selected here as `jev-latest` by default.

## Native Preflight

Check display, monitor capture, OpenCV, and keyboard prerequisites before starting the bot:

```bash
python bot.py --preflight --profile profiles/example_runner.json
```

To skip keyboard initialization during the check:

```bash
python bot.py --preflight --observe-only \
  --profile profiles/example_runner.json
```

Headless Codespaces normally fail this check because the container cannot see the host desktop. That is expected; use `--sim` there or run native mode on a machine attached to the game display.

## Native Run

After preflight succeeds:

```bash
python bot.py --profile profiles/example_runner.json
```

Use observation-only mode before enabling keyboard events:

```bash
python bot.py --observe-only --profile profiles/example_runner.json
```

## Runtime Controls

Capture and decisions run independently. The default configuration captures at 100 Hz and asks for decisions at 10 Hz. A one-slot handoff keeps only the newest state, so slow decisions cannot create an unbounded queue.

```bash
python bot.py --sim \
  --capture-hz 100 \
  --decision-hz 10 \
  --decision-timeout 0.2 \
  --min-confidence 0.90
```

Useful safety controls:

```bash
python bot.py --sim \
  --action-cooldown 0.15 \
  --min-action-interval 0.05 \
  --stop-file /tmp/system1-gamebot.stop
```

`Ctrl+C`, `SIGTERM`, or creating the configured stop file requests an emergency stop. Native key failures also stop the runtime. Decisions below `--min-confidence` become `DO_NOTHING`.

## Game Profiles

Profiles keep game-specific details out of the main loop. The checked-in example is [profiles/example_runner.json](profiles/example_runner.json):

```bash
python bot.py --sim --profile profiles/example_runner.json
```

A profile can define:

- `monitor`: capture rectangle
- `model`: TypeSafe model, default `jev-latest`
- `actions`: logical actions mapped to keys
- `detector`: currently `green_obstacle`
- `detector_config`: HSV bounds, ROI, and minimum contour area
- `min_confidence`: action safety threshold

Example shape:

```json
{
  "name": "example-runner",
  "model": "jev-latest",
  "min_confidence": 0.0,
  "monitor": {"left": 0, "top": 0, "width": 1280, "height": 720},
  "actions": {
    "JUMP": "space",
    "DODGE_LEFT": "left",
    "DODGE_RIGHT": "right",
    "DO_NOTHING": "none"
  },
  "detector": "green_obstacle",
  "detector_config": {
    "hsv_lower": [35, 90, 140],
    "hsv_upper": [90, 255, 255],
    "min_area": 12,
    "roi_top_fraction": 0.333
  }
}
```

## Project Layout

- `bot.py`: runtime orchestration, scheduling, safety, CLI, and telemetry
- `vision.py`: capture plus detector interfaces
- `decision.py`: simulator and TypeSafe decision providers
- `input.py`: simulator, observation-only, and native input backends
- `profiles.py`: profile loading and validation
- `profiles/`: checked-in game profiles
- `tests/`: dependency-free regression tests

## Tests

Run the test suite from the repository root:

```bash
python -m unittest discover -s tests -v
```

Also useful before committing:

```bash
python -m py_compile bot.py decision.py input.py profiles.py vision.py
git diff --check
```

The tests cover simulator state changes, profile validation, bounded state handoff, input suppression, cooldowns, fallback decisions, and TypeSafe response parsing with a fake client.

## Honest Scope

This repository is a foundation for a universal architecture, not a universal game intelligence system. Real support for a game requires:

1. A calibrated screen region.
2. A detector that understands that game's visuals.
3. A profile mapping logical actions to controls.
4. A confidence and timing policy tested against real outcomes.
5. A display, input backend, and permissions that the runtime can access.

The simulator is fully usable in Codespaces. Native mode and live TypeSafe calls still require the external environment described above, and the full 100 Hz see-think-act path must be measured on target hardware rather than assumed.
