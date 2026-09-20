# system1-gamebot

A lightweight, modular gaming-bot pipeline:

1. **See:** `mss` captures a configured screen region and OpenCV extracts compact pixel telemetry.
2. **Think:** the Jev `choice` primitive selects one action from a fixed option set.
3. **Act:** `pynput` sends deterministic keyboard events.

## Requirements

- Python 3.10 or newer
- A graphical display accessible to `mss` and `pynput`
- A Jev SDK installation that provides `jev.Client`
- A `TYPESAFE_API_KEY` environment variable

The pinned `typesafe-ai==0.1.0` dependency is a PyPI redirect shim. It does not provide `jev.Client`; install the official Jev SDK from its provider in the environment where the bot runs.

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

For native screen capture and keyboard events:

```bash
export TYPESAFE_API_KEY="your-api-key"
python bot.py
```

Stop either loop with `Ctrl+C`. Each iteration logs the selected action, the returned probability, and total capture-to-act latency in milliseconds at approximately 10 Hz.

## Configuration

`GameVision` defaults to the primary monitor. To target a smaller region, pass an `mss` monitor dictionary when constructing it:

```python
from vision import GameVision

vision = GameVision({"left": 0, "top": 0, "width": 1280, "height": 720})
```

The sample detector tracks bright green pixels in the lower two-thirds of the capture and serializes threat distance, lane position, speed, and visibility for the decision step. Tune the HSV bounds and region in `vision.py` for the target game.

## GitHub Codespaces

Codespaces containers are normally headless and cannot capture the host desktop or emit host keyboard events by default. Use `python bot.py --sim` for browser-terminal development. Run native mode in a Codespace only after providing an accessible X/Wayland display and the required input permissions; otherwise use a local environment attached to the game display.
