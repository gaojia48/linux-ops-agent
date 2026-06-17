from pathlib import Path
import unittest

from agent.skill_loader import load_skills


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SkillLoaderTest(unittest.TestCase):
    def test_loads_expected_skills(self):
        skills = load_skills(PROJECT_ROOT)

        self.assertLessEqual(
            {"disk_check", "log_analyze", "process_check", "network_check", "health_report"},
            set(skills),
        )
        self.assertEqual(skills["disk_check"].script.name, "disk_check.sh")
        self.assertIn("df", skills["disk_check"].allowed_commands)

    def test_skill_scripts_exist_under_scripts_directory(self):
        skills = load_skills(PROJECT_ROOT)
        scripts_root = PROJECT_ROOT / "scripts"

        for skill in skills.values():
            self.assertTrue(skill.script.exists())
            self.assertTrue(skill.script.resolve().is_relative_to(scripts_root.resolve()))


if __name__ == "__main__":
    unittest.main()
