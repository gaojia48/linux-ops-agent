from pathlib import Path
import unittest

from agent.config import ExecutionConfig
from agent.executor import SkillExecutor
from agent.planner import Plan
from agent.report import create_report
from agent.skill_loader import load_skills


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReportTest(unittest.TestCase):
    def test_create_report_without_llm(self):
        tmp_path = PROJECT_ROOT / "reports" / "test-output"
        skills = load_skills(PROJECT_ROOT)
        skill = skills["process_check"]
        executor = SkillExecutor(
            PROJECT_ROOT,
            ExecutionConfig(script_timeout_seconds=10, reports_dir=tmp_path, allow_high_risk=False),
        )
        result = executor.run(skill)
        plan = Plan(skills=(skill.name,), reason="test", source="test")

        report_path = create_report(
            user_request="检查进程",
            plan=plan,
            selected_skills=[skill],
            results=[result],
            reports_dir=tmp_path,
            use_llm=False,
        )

        content = report_path.read_text(encoding="utf-8")
        self.assertIn("Linux 运维诊断报告", content)
        self.assertIn("process_check", content)


if __name__ == "__main__":
    unittest.main()
