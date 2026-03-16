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

    def test_user_input_interrupt_emits_terminal_reason(self):
        def interrupting_agent(event_emitter=None, **kwargs):
            _ = kwargs
            event_emitter(
                {
                    "type": "user_input_required",
                    "question": "Which environment should I use?",
                    "options": [{"label": "staging"}],
                    "allow_free_text": True,
                    "step": 1,
                }
            )

        events = list(
            stream_agentic(
                client=None,
                model="openai/gpt-5.3-codex",
                message="hello",
                history=[],
                thinking_mode=False,
                emit_reasoning=False,
                run_web_search=lambda *a, **kw: ("", []),
                run_agent=interrupting_agent,
            )
        )

        self.assertTrue(any(event["type"] == "user_input_required" for event in events))
        self.assertEqual(events[-1], {"type": "done", "finish_reason": "user_input_required"})
        self.assertFalse(any(event.get("type") == "context_usage" and event.get("usage", {}).get("phase") == "final" for event in events))


if __name__ == "__main__":
    unittest.main()
