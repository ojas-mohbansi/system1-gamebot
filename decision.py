"""Decision providers for native TypeSafe System One and simulator mode."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol


ACTION_OPTIONS = ("JUMP", "DODGE_LEFT", "DODGE_RIGHT", "DO_NOTHING")


@dataclass(frozen=True)
class Decision:
    action: str
    confidence: float
    probabilities: dict[str, float]


class DecisionProvider(Protocol):
    def decide(self, state: str) -> Decision:
        """Choose one safe action for the current serialized state."""


class DecisionProviderError(RuntimeError):
    """A categorized failure from the TypeSafe decision provider."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


class SimulatorDecisionProvider:
    """Local provider so simulator mode needs no network or API key."""

    def decide(self, state: str) -> Decision:
        distance_match = re.search(r"distance:\s*(\d+)\s*px", state)
        distance = int(distance_match.group(1)) if distance_match else 0
        if distance <= 30:
            return Decision("JUMP", 0.95, {"JUMP": 0.95, "DO_NOTHING": 0.05})
        return Decision("DO_NOTHING", 0.875, {"DO_NOTHING": 0.875, "JUMP": 0.125})


class TypeSafeDecisionProvider:
    """Adapter around the published TypeSafe System One Python SDK."""

    def __init__(
        self,
        api_key: str,
        timeout: float = 0.2,
        model: str = "jev-latest",
        client: Any = None,
        choice_type: Any = None,
    ) -> None:
        if client is None or choice_type is None:
            from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

            choice_type = choice_type or Choice
            client = client or TypeSafeClient(
                api_key=api_key,
                model=model,
                timeout=timeout,
                retry=RetryPolicy(max_retries=0),
            )
        self._model = model
        self._choice_type = choice_type
        self._client = client

    def decide(self, state: str) -> Decision:
        question = self._choice_type(
            instructions="Choose the action that maximizes survival in this game state.",
            criteria={
                "JUMP": "Jump immediately over a nearby obstacle.",
                "DODGE_LEFT": "Move left to avoid an obstacle in the current lane.",
                "DODGE_RIGHT": "Move right to avoid an obstacle in the current lane.",
                "DO_NOTHING": "Take no action because no immediate threat is present.",
            },
        )
        try:
            response = self._client.system_one(
                state={"game_state": state},
                questions={"action": question},
                model=self._model,
            )
        except Exception as error:
            category = type(error).__name__
            raise DecisionProviderError(category, str(error)) from error
        answer = response.choices.get("action")
        if answer is None:
            raise RuntimeError("TypeSafe returned no action answer.")

        action = answer.choice.upper().strip()
        if action not in ACTION_OPTIONS:
            raise ValueError(f"TypeSafe returned unsupported action: {action}")
        return Decision(
            action=action,
            confidence=float(answer.confidence),
            probabilities={
                str(name): float(probability)
                for name, probability in answer.probabilities.items()
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TypeSafeDecisionProvider":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()