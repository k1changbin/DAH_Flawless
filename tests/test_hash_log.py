import unittest

from dah_flawless.environment.hash_log import GENESIS_HASH, attach_hash, verify_hash_chain


class HashLogTests(unittest.TestCase):
    def test_hash_chain_detects_tampering(self):
        first = attach_hash(GENESIS_HASH, {"round": 1, "score": {"winner": "BLUE"}})
        second = attach_hash(first["this_hash"], {"round": 2, "score": {"winner": "BLUE"}})
        chain = [first, second]

        self.assertTrue(verify_hash_chain(chain))

        tampered = [dict(first), dict(second)]
        tampered[0]["score"] = {"winner": "RED_BREACH"}
        self.assertFalse(verify_hash_chain(tampered))


if __name__ == "__main__":
    unittest.main()
