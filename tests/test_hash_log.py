from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dah_flawless.environment.hash_log import GENESIS_HASH, attach_hash, reset_log_outputs, verify_hash_chain


class HashLogTests(unittest.TestCase):
    def test_hash_chain_detects_tampering(self):
        first = attach_hash(GENESIS_HASH, {"round": 1, "score": {"winner": "BLUE"}})
        second = attach_hash(first["this_hash"], {"round": 2, "score": {"winner": "BLUE"}})
        chain = [first, second]

        self.assertTrue(verify_hash_chain(chain))

        tampered = [dict(first), dict(second)]
        tampered[0]["score"] = {"winner": "RED_BREACH"}
        self.assertFalse(verify_hash_chain(tampered))

    def test_reset_log_outputs_deletes_only_selected_files(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "round_logs.jsonl"
            summary_path = root / "summary.json"
            missing_path = root / "missing.json"
            log_path.write_text("old log", encoding="utf-8")
            summary_path.write_text("old summary", encoding="utf-8")

            removed = reset_log_outputs([log_path, summary_path, missing_path, log_path])

            self.assertEqual(removed, [log_path, summary_path])
            self.assertFalse(log_path.exists())
            self.assertFalse(summary_path.exists())
            self.assertFalse(missing_path.exists())

    def test_reset_log_outputs_rejects_directories(self):
        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(IsADirectoryError):
                reset_log_outputs([Path(temp_dir)])


if __name__ == "__main__":
    unittest.main()
