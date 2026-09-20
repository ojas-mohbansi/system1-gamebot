"""Input backends with a common safe action interface."""

from __future__ import annotations

from typing import Protocol

from profiles import GameProfile


class InputController(Protocol):
    def press(self, action: str) -> bool:
        """Send one mapped action and return whether it was accepted."""

    def release_all(self) -> None:
        """Release every key currently held by the backend."""


class SimulatorController:
    def __init__(self, profile: GameProfile) -> None:
        self.profile = profile

    def press(self, action: str) -> bool:
        key_name = self.profile.actions.get(action, "none").upper()
        if key_name == "NONE":
            print("[SIM HANDS] No key press.", flush=True)
        else:
            print(f"[SIM HANDS] Pressing {key_name} key...", flush=True)
        return action in self.profile.actions

    def release_all(self) -> None:
        print("[SIM HANDS] Releasing all keys.", flush=True)


class NullController:
    def press(self, action: str) -> bool:
        print(f"[OBSERVE ONLY] Suppressed {action}.", flush=True)
        return False

    def release_all(self) -> None:
        return None


class PynputController:
    def __init__(self, profile: GameProfile) -> None:
        from pynput import keyboard

        self._keyboard = keyboard
        self._controller = keyboard.Controller()
        self._profile = profile
        self._pressed: set[object] = set()

    def _key_for_action(self, action: str) -> object | None:
        key_name = self._profile.actions.get(action, "none").lower()
        named_keys = {
            "space": self._keyboard.Key.space,
            "left": self._keyboard.Key.left,
            "right": self._keyboard.Key.right,
            "up": self._keyboard.Key.up,
            "down": self._keyboard.Key.down,
            "enter": self._keyboard.Key.enter,
            "esc": self._keyboard.Key.esc,
        }
        key = named_keys.get(key_name)
        if key is None and len(key_name) == 1:
            key = self._keyboard.KeyCode.from_char(key_name)
        return key

    def press(self, action: str) -> bool:
        key = self._key_for_action(action)
        if key is None:
            return action == "DO_NOTHING"
        self._controller.press(key)
        self._pressed.add(key)
        self._controller.release(key)
        self._pressed.discard(key)
        return True

    def release_all(self) -> None:
        for key in tuple(self._pressed):
            try:
                self._controller.release(key)
            finally:
                self._pressed.discard(key)