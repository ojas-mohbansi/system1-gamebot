# system1-gamebot

A lightweight, modular gaming-bot pipeline:

1. **See:** `mss` captures a configured screen region and OpenCV extracts compact pixel telemetry.
2. **Think:** TypeSafe System One's `Choice` primitive selects one action from a fixed option set.
3. **Act:** `pynput` sends deterministic keyboard events.

## Requirements

- Python 3.10 or newer
- A graphical display accessible to `mss` and `pynput`
- The official TypeSafe SDK (`typesafe-sdk==0.7.0`)
- A `TYPESAFE_API_KEY` environment variable

The Python integration uses `TypeSafeClient.system_one()` with the `Choice` primitive. Jev is TypeSafe's System One model; this repository keeps the TypeSafe provider behind a small decision interface.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export TYPESAFE_API_KEY="your-api-key"
```

## Run

For a headless Codespace or browser terminal, use simulator mode:

```bash
python bot.py --sim
```

Simulator mode generates a moving center-lane obstacle, uses a deterministic local choice provider, and prints simulated keyboard actions. It does not require `TYPESAFE_API_KEY`, a graphical display, or native keyboard permissions.

Use observation-only mode to inspect decisions without sending keyboard events:

```bash
python bot.py --sim --observe-only
```

For native screen capture and keyboard events:

```bash
export TYPESAFE_API_KEY="your-api-key"
python bot.py
```

Check native prerequisites without starting the loop or sending actions:

```bash
python bot.py --preflight --observe-only --profile profiles/example_runner.json
```

The default System One model is `jev-latest`; override it explicitly when needed:

```bash
python bot.py --model jev-latest
```

Stop either loop with `Ctrl+C`. Each iteration logs the selected action, confidence, choice probabilities, and total capture-to-act latency in milliseconds at approximately 10 Hz.

Runtime rates and the native decision timeout can be tuned without editing code:

```bash
python bot.py --sim --capture-hz 100 --decision-hz 10 --decision-timeout 0.2
```

Capture and decision work run independently. A bounded one-state handoff drops stale telemetry instead of growing memory, and a slow or failed decision falls back to `DO_NOTHING`. Logs include engine latency, state age, and the fallback reason.

Confidence can be used as an explicit safety policy. Decisions below the threshold become `DO_NOTHING`:

```bash
python bot.py --sim --min-confidence 0.90
```

The default threshold is `0.0`; configure a higher value per profile after measuring the target game.

Phase 3 adds runtime safety controls:

```bash
python bot.py --sim \
	--action-cooldown 0.15 \
	--min-action-interval 0.05 \
	--stop-file /tmp/system1-gamebot.stop
```

Native mode checks for an X11/Wayland display and a working `pynput` controller before starting. `Ctrl+C`, `SIGTERM`, or creating the configured stop file triggers an emergency stop. Keyboard actions are rate-limited and failed key events stop the runtime. Observation-only native mode skips keyboard initialization and suppresses all actions.

## Game Profiles

Use `--profile` to load a game-specific JSON profile without changing the runtime:

```bash
python bot.py --sim --profile profiles/example_runner.json
```

Example profile:

```json
{
	"name": "example-runner",
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

The current detector adapter is `green_obstacle`. Profiles isolate per-game monitor geometry, keyboard mapping, and HSV tuning while keeping the capture, decision, safety, and telemetry runtime shared. Detectors implement a common interface, and input backends can be simulator, observation-only, or native `pynput`.

## Tests

Run the dependency-free verification suite from the repository root:

```bash
python -m unittest discover -s tests -v
```

The suite covers simulated vision state changes, profile loading, bounded state handoff, action cooldowns, simulated actuation, fallback decisions, and the TypeSafe response adapter with a fake client.

## Configuration

`GameVision` defaults to the primary monitor. To target a smaller region, pass an `mss` monitor dictionary when constructing it:

```python
from vision import GameVision

vision = GameVision({"left": 0, "top": 0, "width": 1280, "height": 720})
```

The sample detector tracks bright green pixels in the lower two-thirds of the capture and serializes threat distance, lane position, speed, and visibility for the decision step. Tune the HSV bounds and region in `vision.py` for the target game.

## GitHub Codespaces

Codespaces containers are normally headless and cannot capture the host desktop or emit host keyboard events by default. Use `python bot.py --sim` for browser-terminal development. Run native mode in a Codespace only after providing an accessible X/Wayland display and the required input permissions; otherwise use a local environment attached to the game display.
