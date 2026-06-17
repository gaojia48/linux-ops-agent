from __future__ import annotations

import os
from pathlib import Path

from agent.config import DeepSeekConfig


class DeepSeekClient:
    def __init__(self, config: DeepSeekConfig):
        _load_dotenv_if_available()
        _load_dotenv_manually(Path.cwd() / ".env")
        _sanitize_proxy_env()
        self.config = config
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.model = os.getenv("DEEPSEEK_MODEL", config.model).strip() or config.model
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", config.base_url).strip() or config.base_url
        self._client = None
        self.last_error = ""

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _ensure_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                self.last_error = "当前 Python 环境未安装 openai，请先执行：python3 -m pip install -r requirements.txt"
                raise RuntimeError(self.last_error) from exc

            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def complete(self, prompt: str, system: str | None = None) -> str:
        if not self.available:
            self.last_error = "没有读取到 DEEPSEEK_API_KEY，请检查 .env 是否在项目根目录"
            raise RuntimeError(self.last_error)

        client = self._ensure_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
            timeout=self.config.timeout_seconds,
        )
        return response.choices[0].message.content or ""

    def summarize_report(self, user_request: str, raw_output: str) -> str:
        system = (
            "你是 Linux 运维诊断助手。请根据命令输出写出简洁、可答辩展示的中文报告。"
            "报告必须包含：问题概述、关键证据、可能原因、建议处理步骤、涉及的 Linux 命令、风险提示。"
        )
        prompt = (
            f"用户请求：{user_request}\n\n"
            "以下是受控 Shell 脚本的输出，请生成诊断报告：\n"
            f"{raw_output[:12000]}"
        )
        return self.complete(prompt, system=system)


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _load_dotenv_manually(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _sanitize_proxy_env() -> None:
    has_http_proxy = bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"))
    for key in ("ALL_PROXY", "all_proxy"):
        value = os.environ.get(key, "")
        if value.lower().startswith("socks://") and has_http_proxy:
            os.environ.pop(key, None)
