import os
from pathlib import Path
import subprocess
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LogAnalyzeScriptTest(unittest.TestCase):
    def test_log_analyze_uses_sample_auth_log(self):
        env = os.environ.copy()
        env["AUTH_LOG_FILE"] = str(PROJECT_ROOT / "tests" / "sample_logs" / "auth.log")

        result = subprocess.run(
            ["bash", "scripts/log_analyze.sh"],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Using auth log:", result.stdout)
        self.assertIn("203.0.113.10", result.stdout)
        self.assertIn("198.51.100.20", result.stdout)
        self.assertIn("Failed password", result.stdout)


if __name__ == "__main__":
    unittest.main()
