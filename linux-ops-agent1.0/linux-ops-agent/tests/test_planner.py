from pathlib import Path
import unittest

from agent.planner import Planner
from agent.skill_loader import load_skills


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PlannerTest(unittest.TestCase):
    def test_keyword_planner_selects_disk_check(self):
        planner = Planner(load_skills(PROJECT_ROOT))

        plan = planner.plan("检查磁盘空间问题", use_llm=False)

        self.assertFalse(plan.refused)
        self.assertIn("disk_check", plan.skills)
        self.assertNotIn("health_report", plan.skills)
        self.assertEqual(plan.source, "keyword")

    def test_keyword_planner_selects_log_analyze(self):
        planner = Planner(load_skills(PROJECT_ROOT))

        plan = planner.plan("分析最近 SSH 登录失败", use_llm=False)

        self.assertFalse(plan.refused)
        self.assertIn("log_analyze", plan.skills)

    def test_planner_refuses_dangerous_request(self):
        planner = Planner(load_skills(PROJECT_ROOT))

        plan = planner.plan("删除所有日志并重启服务器", use_llm=False)

        self.assertTrue(plan.refused)
        self.assertFalse(plan.skills)
        self.assertIn("不会自动执行", plan.refusal_reason)

    def test_keyword_planner_does_not_default_to_health_report(self):
        planner = Planner(load_skills(PROJECT_ROOT))

        plan = planner.plan("0", use_llm=False)

        self.assertFalse(plan.refused)
        self.assertFalse(plan.skills)
        self.assertEqual(plan.source, "keyword")
        self.assertIn("不执行任何 skill", plan.reason)

    def test_llm_planner_can_return_normal_answer_without_skills(self):
        class FakeClient:
            available = True

            def complete(self, prompt):
                return '{"skills":[],"reason":"未触发运维 skill","answer":"你输入的是 0，没有明确运维需求。"}'

        planner = Planner(load_skills(PROJECT_ROOT), llm_client=FakeClient())

        plan = planner.plan("0", use_llm=True)

        self.assertFalse(plan.refused)
        self.assertFalse(plan.skills)
        self.assertEqual(plan.source, "deepseek")
        self.assertIn("没有明确运维需求", plan.answer)


if __name__ == "__main__":
    unittest.main()
