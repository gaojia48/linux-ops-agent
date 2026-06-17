from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DeepSeekConfig:
    base_url: str
    model: str
    timeout_seconds: int


@dataclass(frozen=True)
class ExecutionConfig:
    script_timeout_seconds: int
    reports_dir: Path
    allow_high_risk: bool


@dataclass(frozen=True)
class AgentConfig:
    fallback_to_keywords: bool
    max_skills_per_request: int


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    deepseek: DeepSeekConfig
    execution: ExecutionConfig
    agent: AgentConfig


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config file must contain a YAML object: {path}")
    return data


def load_config(project_root: Path) -> AppConfig:
    data = _read_yaml(project_root / "config.yaml")
    deepseek = data.get("deepseek", {})
    execution = data.get("execution", {})
    agent = data.get("agent", {})

    return AppConfig(
        project_root=project_root,
        deepseek=DeepSeekConfig(
            base_url=str(deepseek.get("base_url", "https://api.deepseek.com")),
            model=str(deepseek.get("model", "deepseek-v4-flash")),
            timeout_seconds=int(deepseek.get("timeout_seconds", 30)),
        ),
        execution=ExecutionConfig(
            script_timeout_seconds=int(execution.get("script_timeout_seconds", 25)),
            reports_dir=project_root / str(execution.get("reports_dir", "reports")),
            allow_high_risk=bool(execution.get("allow_high_risk", False)),
        ),
        agent=AgentConfig(
            fallback_to_keywords=bool(agent.get("fallback_to_keywords", True)),
            max_skills_per_request=int(agent.get("max_skills_per_request", 3)),
        ),
    )
