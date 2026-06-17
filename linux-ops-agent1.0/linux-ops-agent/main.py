#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
from pathlib import Path

from agent.config import load_config
from agent.executor import SkillExecutor, UnsafeSkillError
from agent.llm_client import DeepSeekClient
from agent.planner import Planner
from agent.report import create_report
from agent.skill_loader import load_skills


PROJECT_ROOT = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Linux 运维诊断 Agent Skills 系统")
    parser.add_argument("request", nargs="*", help="自然语言运维问题，例如：检查磁盘空间问题")
    parser.add_argument("--interactive", "-i", action="store_true", help="进入交互模式，连续输入运维问题")
    parser.add_argument("--list-skills", action="store_true", help="列出可用 skills")
    parser.add_argument("--skill", help="直接执行指定 skill")
    parser.add_argument("--report", choices=["daily"], help="生成固定巡检报告")
    parser.add_argument("--no-llm", action="store_true", help="禁用 DeepSeek，使用本地关键词模式")
    return parser


def list_skills(skills) -> None:
    for skill in skills.values():
        print(f"- {skill.name}: {skill.description} [{skill.risk_level}]")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.interactive:
        return interactive_main(use_llm=not args.no_llm)

    config = load_config(PROJECT_ROOT)
    skills = load_skills(PROJECT_ROOT)

    if args.list_skills:
        list_skills(skills)
        return 0

    user_request = " ".join(args.request).strip()
    selected_names: tuple[str, ...]
    plan = None
    use_llm = not args.no_llm
    llm_client = DeepSeekClient(config.deepseek)

    if user_request.lower() in {"doctor", "check env", "自检", "环境检查"}:
        return _run_doctor()

    if args.skill:
        if args.skill not in skills:
            print(f"Unknown skill: {args.skill}", file=sys.stderr)
            return 2
        from agent.planner import Plan

        selected_names = (args.skill,)
        plan = Plan(skills=selected_names, reason="用户指定 skill", source="manual")
        user_request = user_request or f"执行 {args.skill}"
    elif args.report == "daily":
        from agent.planner import Plan

        selected_names = ("health_report",)
        plan = Plan(skills=selected_names, reason="用户请求每日巡检报告", source="manual")
        user_request = user_request or "生成今日服务器巡检报告"
    else:
        if not user_request:
            print("Please provide a request, --skill, --report daily, or --list-skills.", file=sys.stderr)
            return 2
        planner = Planner(
            skills,
            llm_client=llm_client,
            max_skills=config.agent.max_skills_per_request,
        )
        plan = planner.plan(user_request, use_llm=use_llm)
        if use_llm and plan.source != "deepseek":
            if llm_client.last_error:
                print(f"DeepSeek 未启用，已回退本地模式：{llm_client.last_error}")
            elif not llm_client.available:
                print("DeepSeek 未启用，已回退本地模式：没有读取到 DEEPSEEK_API_KEY")
        if plan.refused:
            print(f"拒绝执行：{plan.refusal_reason}")
            return 1
        selected_names = plan.skills

    selected_skills = [skills[name] for name in selected_names if name in skills]
    if not selected_skills:
        print(f"请求：{user_request}")
        print(f"选择方式：{plan.source}")
        print(f"选择原因：{plan.reason}")
        print("执行 skills：无")
        if plan.answer:
            print()
            print(plan.answer)
        else:
            print()
            print("没有匹配到明确的 Linux 运维 skill，因此没有执行任何脚本。")
            if use_llm and llm_client.last_error:
                print(f"DeepSeek 普通回答不可用：{llm_client.last_error}")
        return 0

    print(f"请求：{user_request}")
    print(f"选择方式：{plan.source}")
    print(f"选择原因：{plan.reason}")
    print(f"执行 skills：{', '.join(skill.name for skill in selected_skills)}")
    print()

    executor = SkillExecutor(PROJECT_ROOT, config.execution)
    results = []
    for skill in selected_skills:
        try:
            result = executor.run(skill)
        except UnsafeSkillError as exc:
            print(f"[{skill.name}] refused: {exc}", file=sys.stderr)
            continue
        results.append(result)
        status = "OK" if result.ok else "FAILED"
        print(f"[{skill.name}] {status} exit={result.exit_code} duration={result.duration_seconds:.2f}s")
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)

    if not results:
        print("No skill results were produced.", file=sys.stderr)
        return 1

    report_path = create_report(
        user_request=user_request,
        plan=plan,
        selected_skills=selected_skills,
        results=results,
        reports_dir=config.execution.reports_dir,
        llm_client=llm_client,
        use_llm=use_llm,
    )

    print()
    print(f"报告已生成：{report_path}")
    print(report_path.read_text(encoding="utf-8")[:4000])
    return 0 if all(result.ok for result in results) else 1


def interactive_main(use_llm: bool = True) -> int:
    print("Linux Ops Agent 交互模式")
    print("直接输入问题，例如：检查磁盘空间问题")
    print("输入 help 查看命令，输入 exit 退出。")
    print()

    while True:
        try:
            text = input("ops> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not text:
            continue
        if text in {"exit", "quit", "退出", "q"}:
            return 0
        if text in {"help", "帮助", "?"}:
            _print_interactive_help()
            code = 0
        elif text in {"list", "skills", "技能"}:
            code = main(["--list-skills"])
        elif text in {"reports", "ls reports", "报告列表"}:
            code = _list_reports()
        elif text in {"last report", "last", "latest report", "最新报告", "查看最新报告"}:
            code = _show_last_report()
        elif text in {"doctor", "check env", "自检", "环境检查"}:
            code = _run_doctor()
        elif text in {"clear reports", "clean reports", "清空报告", "清除报告"}:
            code = _clear_reports()
        elif text in {"daily", "report", "巡检", "报告"}:
            args = ["--report", "daily"]
            if not use_llm:
                args.append("--no-llm")
            code = main(args)
        else:
            args = [text]
            if not use_llm:
                args.append("--no-llm")
            code = main(args)

        print(f"\n本次执行完成，退出码：{code}\n")


def _print_interactive_help() -> None:
    print("可用命令：")
    print("  list              查看 skills")
    print("  reports           查看已生成报告")
    print("  last report       查看最新报告内容")
    print("  doctor            检查运行环境和配置")
    print("  clear reports     清空 reports 目录里的报告")
    print("  daily             生成综合巡检报告")
    print("  exit              退出")
    print("也可以直接输入自然语言问题，例如：检查磁盘空间问题")


def _list_reports() -> int:
    reports_dir = PROJECT_ROOT / "reports"
    if not reports_dir.exists():
        print("reports 目录还不存在。")
        return 0

    reports = sorted(reports_dir.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not reports:
        print("reports 目录里没有报告。")
        return 0

    for path in reports:
        size_kb = path.stat().st_size / 1024
        print(f"- {path.name} ({size_kb:.1f} KB)")
    return 0


def _show_last_report() -> int:
    report = _find_latest_report(PROJECT_ROOT / "reports")
    if not report:
        print("reports 目录里没有报告。")
        return 0

    print(f"最新报告：{report.name}")
    print()
    print(report.read_text(encoding="utf-8"))
    return 0


def _find_latest_report(reports_dir: Path) -> Path | None:
    if not reports_dir.exists():
        return None
    reports = [path for path in reports_dir.glob("*.md") if path.is_file()]
    if not reports:
        return None
    return max(reports, key=lambda path: path.stat().st_mtime)


def _run_doctor() -> int:
    print("Linux Ops Agent 环境自检")
    print()

    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python 版本", sys.version_info >= (3, 10), sys.version.split()[0]))
    checks.append(("项目目录", PROJECT_ROOT.exists(), str(PROJECT_ROOT)))

    config_ok = True
    try:
        config = load_config(PROJECT_ROOT)
        checks.append(("config.yaml", True, "已加载"))
    except Exception as exc:
        config_ok = False
        config = None
        checks.append(("config.yaml", False, str(exc)))

    try:
        skills = load_skills(PROJECT_ROOT)
        checks.append(("skills 配置", True, f"{len(skills)} 个 skill"))
    except Exception as exc:
        skills = {}
        checks.append(("skills 配置", False, str(exc)))

    for module in ("openai", "dotenv", "yaml", "pytest"):
        checks.append((f"Python 依赖 {module}", importlib.util.find_spec(module) is not None, module))

    if config_ok and config:
        llm_client = DeepSeekClient(config.deepseek)
        checks.append(("DeepSeek API Key", llm_client.available, "已读取" if llm_client.available else "未读取"))
        checks.append(("DeepSeek base_url", bool(llm_client.base_url), llm_client.base_url))
        checks.append(("DeepSeek model", bool(llm_client.model), llm_client.model))

    proxy_parts = []
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value = os.environ.get(key)
        if value:
            proxy_parts.append(f"{key}={value}")
    checks.append(("代理环境变量", True, "; ".join(proxy_parts) if proxy_parts else "未设置"))

    for command in ("bash", "df", "du", "find", "grep", "sed", "awk", "ps", "ss", "ip", "ping", "journalctl"):
        checks.append((f"Linux 命令 {command}", shutil.which(command) is not None, shutil.which(command) or "未找到"))

    scripts_dir = PROJECT_ROOT / "scripts"
    script_paths = sorted(scripts_dir.glob("*.sh"))
    checks.append(("scripts 目录", bool(script_paths), f"{len(script_paths)} 个脚本"))
    for script in script_paths:
        checks.append((f"脚本可执行 {script.name}", os.access(script, os.X_OK), str(script)))

    failed = 0
    for name, ok, detail in checks:
        mark = "OK" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{mark}] {name}: {detail}")

    print()
    if failed:
        print(f"自检完成：发现 {failed} 个问题。")
        return 1
    print("自检完成：环境看起来正常。")
    return 0


def _clear_reports() -> int:
    reports_dir = PROJECT_ROOT / "reports"
    if not reports_dir.exists():
        print("reports 目录还不存在。")
        return 0

    removed = 0
    for path in reports_dir.glob("*.md"):
        path.unlink()
        removed += 1

    test_output = reports_dir / "test-output"
    if test_output.exists():
        shutil.rmtree(test_output)

    print(f"已清除 {removed} 个报告文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
