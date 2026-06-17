from pathlib import Path
import unittest

from agent.config import ExecutionConfig
from agent.executor import SkillExecutor, UnsafeSkillError
from agent.skill_loader import Skill, load_skills


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path: Path) -> ExecutionConfig:
    return ExecutionConfig(script_timeout_seconds=10, reports_dir=tmp_path, allow_high_risk=False)


class ExecutorTest(unittest.TestCase):
    def test_executor_runs_disk_check(self):
        tmp_path = PROJECT_ROOT / "reports" / "test-output"
        skills = load_skills(PROJECT_ROOT)
        executor = SkillExecutor(PROJECT_ROOT, _config(tmp_path))

        result = executor.run(skills["disk_check"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Disk usage", result.stdout)

    def test_executor_rejects_script_outside_scripts(self):
        tmp_path = PROJECT_ROOT / "reports" / "test-output"
        executor = SkillExecutor(PROJECT_ROOT, _config(tmp_path))
        skill = Skill(
            name="bad",
            description="bad",
            script=PROJECT_ROOT / "README.md",
            risk_level="low",
            allowed_commands=("cat",),
            keywords=(),
            inputs=(),
        )

        with self.assertRaises(UnsafeSkillError):
            executor.run(skill)


if __name__ == "__main__":
    unittest.main()
