import contextlib
import io
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from bot import ActionLimiter, LatestStateQueue, StateSnapshot, actuate, fallback_decision
from decision import TypeSafeDecisionProvider
from profiles import GameProfile, load_profile
from vision import GameVision


class FakeChoice:
    def __init__(self, instructions, criteria):
        self.instructions = instructions
        self.criteria = criteria


class FakeClient:
    def __init__(self):
        self.closed = False
        self.state = None
        self.questions = None

    def system_one(self, *, state, questions):
        self.state = state
        self.questions = questions
        answer = SimpleNamespace(
            choice="JUMP",
            confidence=0.91,
            probabilities={"JUMP": 0.91, "DO_NOTHING": 0.09},
        )
        return SimpleNamespace(choices={"action": answer})

    def close(self):
        self.closed = True


class System1Tests(unittest.TestCase):
    def test_simulator_vision_serializes_moving_distance(self):
        with GameVision(simulator_mode=True) as vision:
            vision.capture_and_process_frame()
            self.assertEqual(
                vision.get_serialized_state(),
                "Obstacle in Center lane, distance: 100 px",
            )
            vision.capture_and_process_frame()
            self.assertEqual(
                vision.get_serialized_state(),
                "Obstacle in Center lane, distance: 95 px",
            )

    def test_profile_round_trip(self):
        profile = GameProfile.from_dict(
            {
                "name": "test-runner",
                "actions": {"JUMP": "x"},
                "detector_config": {"min_area": 24},
            }
        )
        self.assertEqual(profile.name, "test-runner")
        self.assertEqual(profile.actions["JUMP"], "x")
        self.assertEqual(profile.detector_config["min_area"], 24)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text('{"name": "from-file"}', encoding="utf-8")
            self.assertEqual(load_profile(str(path)).name, "from-file")

    def test_latest_state_queue_drops_stale_state(self):
        states = LatestStateQueue()
        states.put_latest(StateSnapshot("old", 0.0, 0.0))
        states.put_latest(StateSnapshot("new", 1.0, 1.0))
        self.assertEqual(states.get(0.01).state, "new")

    def test_action_limiter_blocks_repeated_action(self):
        limiter = ActionLimiter(min_interval=0.0, cooldown=1.0)
        self.assertTrue(limiter.allows("JUMP"))
        self.assertFalse(limiter.allows("JUMP"))
        self.assertTrue(limiter.allows("DO_NOTHING"))

    def test_simulated_actuation_uses_profile_mapping(self):
        output = io.StringIO()
        profile = GameProfile.from_dict({"actions": {"JUMP": "x"}})
        with contextlib.redirect_stdout(output):
            sent = actuate(
                None,
                "JUMP",
                True,
                profile,
                ActionLimiter(0.0, 0.0),
                threading.Event(),
            )
        self.assertTrue(sent)
        self.assertIn("Pressing X key", output.getvalue())

    def test_fallback_is_do_nothing(self):
        decision = fallback_decision("timeout")
        self.assertEqual(decision.action, "DO_NOTHING")
        self.assertEqual(decision.confidence, 0.0)

    def test_typesafe_response_adapter(self):
        fake_client = FakeClient()
        provider = TypeSafeDecisionProvider(
            "unused",
            client=fake_client,
            choice_type=FakeChoice,
        )
        decision = provider.decide("Obstacle in Center lane, distance: 20 px")
        provider.close()

        self.assertEqual(decision.action, "JUMP")
        self.assertAlmostEqual(decision.confidence, 0.91)
        self.assertEqual(fake_client.state["game_state"], "Obstacle in Center lane, distance: 20 px")
        self.assertEqual(set(fake_client.questions), {"action"})
        self.assertTrue(fake_client.closed)


if __name__ == "__main__":
    unittest.main()