import json
import os
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("RESEARCH_NOTES_CONFIG_DIR")
        os.environ["RESEARCH_NOTES_CONFIG_DIR"] = str(Path(self.tmp.name) / "cfg")

    def tearDown(self):
        if self.old is None:
            os.environ.pop("RESEARCH_NOTES_CONFIG_DIR", None)
        else:
            os.environ["RESEARCH_NOTES_CONFIG_DIR"] = self.old
        self.tmp.cleanup()

    def test_save_and_remember(self):
        self.assertEqual(config.load_profiles(), [])
        cfg = {"project": "ABC 과제 (A0000000)", "prefix": "ABC", "pi": "홍길동 책임",
               "author": "홍길동", "repos": ["/tmp/r1"]}
        out = Path(self.tmp.name) / "out"
        path = config.save_run(out, cfg)
        self.assertEqual(path, out / "research-notes.json")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["prefix"], "ABC")
        self.assertEqual(len(config.load_profiles()), 1)
        config.save_run(out, dict(cfg, pi="김철수 책임"))
        profiles = config.load_profiles()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["pi"], "김철수 책임")


if __name__ == "__main__":
    unittest.main()
