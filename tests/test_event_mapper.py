import unittest
from unittest.mock import patch

from backend.event_mapper import stream_agentic, _AGENT_TIMEOUT_S


class TestStreamAgenticTimeout(unittest.TestCase):
    def test_agent_timeout_emits_error_and_done(self):
        """When the agent thread exceeds the deadline, error + done events are emitted."""

        def hanging_agent(**kwargs):
            import time
            time.sleep(5)  # Simulate a hang (will be cut by timeout)

        # Patch _AGENT_TIMEOUT_S to a tiny value for fast testing
        with patch("backend.event_mapper._AGENT_TIMEOUT_S", 0.2):
            events = list(
                stream_agentic(
                    client=None,
                    model="openai/gpt-5.3-codex",
                    message="hello",
                    history=[],
                    thinking_mode=False,
                    emit_reasoning=False,
                    run_web_search=lambda *a, **kw: ("", []),
                    run_agent=hanging_agent,
                )
            )

        event_types = [e["type"] for e in events]
        self.assertIn("error", event_types)
        self.assertIn("done", event_types)
        # error should precede done
        error_idx = event_types.index("error")
        done_idx = event_types.index("done")
        self.assertLess(error_idx, done_idx)
        # done should have finish_reason=error
        done_event = events[done_idx]
        self.assertEqual(done_event["finish_reason"], "error")


if __name__ == "__main__":
    unittest.main()
