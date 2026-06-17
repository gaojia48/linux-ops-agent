from __future__ import annotations

import json
import re
from dataclasses import dataclass

from agent.llm_client import DeepSeekClient
from agent.skill_loader import Skill


DANGEROUS_PATTERNS = (
    r"\brm\s+-rf\b",
    r"删除所有",
    r"清空",
    r"格式化",
    r"\bmkfs\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"重启服务器",
    r"关闭服务器",
)


@dataclass(frozen=True)
class Plan:
    skills: tuple[str, ...]
    reason: str
    refused: bool = False
    refusal_reason: str = ""
    source: str = "keyword"
    answer: str = ""


class Planner:
    def __init__(
        self,
        skills: dict[str, Skill],
        llm_client: DeepSeekClient | None = None,
        max_skills: int = 3,
    ):
        self.skills = skills
        self.llm_client = llm_client
        self.max_skills = max_skills

    def plan(self, user_request: str, use_llm: bool = True) -> Plan:
        if self._looks_dangerous(user_request):
            return Plan(
                skills=(),
                reason="请求包含高风险系统操作",
                refused=True,
                refusal_reason="系统不会自动执行删除、格式化、关机、重启等破坏性操作。",
                source="safety",
            )

        if use_llm and self.llm_client and self.llm_client.available:
            llm_plan = self._plan_with_llm(user_request)
            if llm_plan:
                return llm_plan

        return self._plan_with_keywords(user_request)

    def _looks_dangerous(self, text: str) -> bool:
        lowered = text.lower()
        return any(re.search(pattern, lowered) for pattern in DANGEROUS_PATTERNS)

    def _plan_with_llm(self, user_request: str) -> Plan | None:
        skill_catalog = [
            {
                "name": skill.name,
                "description": skill.description,
                "risk_level": skill.risk_level,
                "keywords": list(skill.keywords),
            }
            for skill in self.skills.values()
        ]
        prompt = (
            "你是 Linux 运维 Agent 路由器。你只能从给定 skills 中选择 skill，禁止输出任意 Shell 命令。\n"
            "只有用户明确提出 Linux 运维诊断、巡检、日志、进程、网络、磁盘等需求时，才选择 skill。\n"
            "如果用户输入无意义内容、闲聊、普通知识问题，或者没有明确触发任何 skill，必须返回空 skills，"
            "并在 answer 字段中正常回答用户。不要为了有结果而默认选择 health_report。\n"
            "必须只返回 JSON，格式为："
            '{"skills":["disk_check"],"reason":"用户想检查磁盘空间","answer":""} '
            '或 {"skills":[],"reason":"未触发运维 skill","answer":"你的回答"}。\n'
            f"最多选择 {self.max_skills} 个 skill。\n"
            f"可用 skills: {json.dumps(skill_catalog, ensure_ascii=False)}\n"
            f"用户请求: {user_request}"
        )
        try:
            raw = self.llm_client.complete(prompt)
            parsed = _parse_json_object(raw)
            selected = tuple(
                name
                for name in parsed.get("skills", [])
                if isinstance(name, str) and name in self.skills
            )[: self.max_skills]
            if selected:
                return Plan(
                    skills=selected,
                    reason=str(parsed.get("reason", "DeepSeek selected matching skills")),
                    source="deepseek",
                )
            return Plan(
                skills=(),
                reason=str(parsed.get("reason", "DeepSeek 未选择可执行 skill")),
                source="deepseek",
                answer=str(parsed.get("answer", "")).strip(),
            )
        except Exception:
            return None

    def _plan_with_keywords(self, user_request: str) -> Plan:
        lowered = user_request.lower()
        scores: list[tuple[int, str]] = []
        for skill in self.skills.values():
            score = 0
            for keyword in skill.keywords:
                if keyword and _keyword_matches(keyword, lowered):
                    score += 2
            for token in re.split(r"\W+", skill.name.lower()):
                if token and token in lowered:
                    score += 1
            if score:
                scores.append((score, skill.name))

        if not scores:
            return Plan(skills=(), reason="未命中明确关键词，不执行任何 skill", source="keyword")

        selected = tuple(name for _, name in sorted(scores, reverse=True)[: self.max_skills])
        return Plan(skills=selected, reason="本地关键词匹配选择 skill", source="keyword")


def _parse_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response does not contain a JSON object")
    return json.loads(text[start : end + 1])


def _keyword_matches(keyword: str, text: str) -> bool:
    if keyword.isascii() and re.fullmatch(r"[a-z0-9_+-]+", keyword):
        if len(keyword) <= 3:
            return re.search(rf"(?<![a-z0-9_+-]){re.escape(keyword)}(?![a-z0-9_+-])", text) is not None
        return keyword in text
    return keyword in text
