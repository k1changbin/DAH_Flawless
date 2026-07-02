import unittest

from dah_flawless.environment.redaction import assert_no_world, redact_state
from dah_flawless.environment.state_factory import create_baseline_state


class RedactionTests(unittest.TestCase):
    def test_redacted_state_has_no_world(self):
        state = create_baseline_state(seed=42)
        redacted = redact_state(state)
        self.assertNotIn("world", redacted)
        assert_no_world(redacted)


if __name__ == "__main__":
    unittest.main()
