from pathlib import Path
import tempfile
import time
import unittest

from main import _find_latest_report


class MainHelpersTest(unittest.TestCase):
    def test_find_latest_report_returns_none_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(_find_latest_report(Path(tmp)))

    def test_find_latest_report_returns_newest_markdown_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "older.md"
            newer = root / "newer.md"
            ignored = root / "ignored.txt"

            older.write_text("older", encoding="utf-8")
            time.sleep(0.01)
            newer.write_text("newer", encoding="utf-8")
            ignored.write_text("ignored", encoding="utf-8")

            self.assertEqual(_find_latest_report(root), newer)


if __name__ == "__main__":
    unittest.main()
