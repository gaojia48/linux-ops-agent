from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from agent.config import ExecutionConfig
from agent.skill_loader import Skill


class UnsafeSkillError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionResult:
    skill_name: str
    script: Path
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class SkillExecutor:
    def __init__(self, project_root: Path, config: ExecutionConfig):
        self.project_root = project_root.resolve()
        self.config = config
        self.scripts_root = (self.project_root / "scripts").resolve()

    def _validate(self, skill: Skill) -> None:
        script = skill.script.resolve()
        if not str(script).startswith(str(self.scripts_root) + "/"):
            raise UnsafeSkillError(f"skill script must be under scripts/: {skill.script}")
        if skill.risk_level == "high" and not self.config.allow_high_risk:
            raise UnsafeSkillError(f"high-risk skill is disabled by config: {skill.name}")

    def run(self, skill: Skill) -> ExecutionResult:
        self._validate(skill)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                ["bash", str(skill.script)],
                cwd=self.project_root,
                text=True,
                capture_output=True,
                timeout=self.config.script_timeout_seconds,
                check=False,
            )
            return ExecutionResult(
                skill_name=skill.name,
                script=skill.script,
                stdout=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
                duration_seconds=time.monotonic() - started,
            )
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                skill_name=skill.name,
                script=skill.script,
                stdout=exc.stdout or "",
                stderr=(exc.stderr or "") + f"\nTimed out after {self.config.script_timeout_seconds}s",
                exit_code=124,
                duration_seconds=time.monotonic() - started,
                timed_out=True,
            )
