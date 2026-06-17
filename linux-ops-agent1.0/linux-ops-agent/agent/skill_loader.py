from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SkillInput:
    name: str
    type: str
    default: Any | None = None
    required: bool = False


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    script: Path
    risk_level: str
    allowed_commands: tuple[str, ...]
    keywords: tuple[str, ...]
    inputs: tuple[SkillInput, ...]


def _load_skill_file(path: Path, project_root: Path) -> Skill:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"skill file must contain a YAML object: {path}")

    required_fields = ("name", "description", "script", "risk_level", "allowed_commands")
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise ValueError(f"{path} missing required fields: {', '.join(missing)}")

    name = str(data["name"])
    script = project_root / str(data["script"])
    allowed_commands = tuple(str(item) for item in data.get("allowed_commands", []))
    if not allowed_commands:
        raise ValueError(f"{path} must declare at least one allowed command")

    raw_inputs = data.get("inputs", {}) or {}
    if not isinstance(raw_inputs, dict):
        raise ValueError(f"{path} inputs must be a YAML object")
    inputs = tuple(
        SkillInput(
            name=str(input_name),
            type=str(input_data.get("type", "string")) if isinstance(input_data, dict) else "string",
            default=input_data.get("default") if isinstance(input_data, dict) else None,
            required=bool(input_data.get("required", False)) if isinstance(input_data, dict) else False,
        )
        for input_name, input_data in raw_inputs.items()
    )

    return Skill(
        name=name,
        description=str(data["description"]),
        script=script,
        risk_level=str(data["risk_level"]).lower(),
        allowed_commands=allowed_commands,
        keywords=tuple(str(item).lower() for item in data.get("keywords", [])),
        inputs=inputs,
    )


def load_skills(project_root: Path, skills_dir: Path | None = None) -> dict[str, Skill]:
    root = skills_dir or project_root / "skills"
    if not root.exists():
        raise FileNotFoundError(f"skills directory not found: {root}")

    skills: dict[str, Skill] = {}
    for path in sorted(root.glob("*.yaml")):
        skill = _load_skill_file(path, project_root)
        if skill.name in skills:
            raise ValueError(f"duplicate skill name: {skill.name}")
        if not skill.script.exists():
            raise FileNotFoundError(f"script for skill {skill.name} not found: {skill.script}")
        if not skill.script.is_file():
            raise ValueError(f"script for skill {skill.name} is not a file: {skill.script}")
        skills[skill.name] = skill

    if not skills:
        raise ValueError(f"no skills found in {root}")
    return skills
