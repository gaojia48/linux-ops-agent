# Planner 意图路由层开发与 DeepSeek LLM 接口对接

> 负责人：AI Agent 接入组
> 涉及文件：`agent/llm_client.py`、`agent/planner.py`、`agent/skill_loader.py`

---

## 1. 模块概述

本模块是 Linux Ops Agent 系统的"大脑"，负责将用户的自然语言输入转换为可执行的运维 skill 选择。核心目标是：

- **理解用户意图**：通过 DeepSeek LLM 识别用户想做什么运维操作
- **安全路由**：只选择预先登记的 skill，拒绝危险请求
- **优雅降级**：DeepSeek 不可用时自动切换本地关键词匹配

模块由三个文件协作完成：

```
skills/*.yaml  ──加载──▶  skill_loader.py  ──Skill 对象字典──▶  planner.py  ◀──API 调用──  llm_client.py  ◀──HTTP──  DeepSeek
   (数据定义)                  (数据层)                       (决策层)                     (通信层)               (云端模型)
```

---

## 2. 通信层 — DeepSeek LLM 客户端（llm_client.py）

### 2.1 初始化：三层环境加载

```python
class DeepSeekClient:
    def __init__(self, config: DeepSeekConfig):
        _load_dotenv_if_available()                # 第 1 层
        _load_dotenv_manually(Path.cwd() / ".env") # 第 2 层
        _sanitize_proxy_env()                      # 第 3 层
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.model   = os.getenv("DEEPSEEK_MODEL", config.model).strip()
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", config.base_url).strip()
        self._client = None
        self.last_error = ""
```

#### 三层加载的设计理由

| 层级 | 函数 | 作用 | 失败处理 |
|---|---|---|---|
| 第 1 层 | `_load_dotenv_if_available()` | 优先使用 `python-dotenv` 库加载 `.env` | 库未安装→静默跳过，不阻断启动 |
| 第 2 层 | `_load_dotenv_manually()` | 手动逐行解析 `.env`，作为第一层的兜底 | 文件不存在→跳过；已有环境变量→不覆盖 |
| 第 3 层 | `_sanitize_proxy_env()` | 修复 SOCKS 代理与 openai SDK 兼容冲突 | 无冲突→无操作 |

**第 1 层** — 优先用库：

```python
def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()
```

**第 2 层** — 手动解析兜底（关键行有注释）：

```python
def _load_dotenv_manually(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue                                    # 跳过注释、空行、非法行
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")     # 去除引号包裹
        if key and key not in os.environ:               # 已有环境变量优先
            os.environ[key] = value
```

**第 3 层** — 修复代理冲突：

```python
def _sanitize_proxy_env() -> None:
    has_http_proxy = bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"))
    for key in ("ALL_PROXY", "all_proxy"):
        value = os.environ.get(key, "")
        if value.lower().startswith("socks://") and has_http_proxy:
            os.environ.pop(key, None)   # 移除冲突的 SOCKS 代理
```

### 2.2 连接方式：OpenAI 兼容 SDK 复用

DeepSeek API 完全兼容 OpenAI SDK 接口规范（`/v1/chat/completions`），直接复用 `openai` Python 包：

```python
def _ensure_client(self):
    if self._client is None:                    # ← 延迟初始化
        try:
            from openai import OpenAI
        except ImportError as exc:
            self.last_error = "当前 Python 环境未安装 openai，请先执行：pip install -r requirements.txt"
            raise RuntimeError(self.last_error) from exc

        self._client = OpenAI(
            api_key=self.api_key,               # DEEPSEEK_API_KEY
            base_url=self.base_url,             # https://api.deepseek.com
        )
    return self._client
```

延迟初始化的好处：当用户执行 `./ops doctor`（环境自检）或 `--no-llm` 模式时，不会触发 `import openai`，避免了不必要的依赖错误。

### 2.3 API 调用参数设计

```python
def complete(self, prompt: str, system: str | None = None) -> str:
    if not self.available:                  # API Key 为空则提前拒绝
        self.last_error = "没有读取到 DEEPSEEK_API_KEY，请检查 .env"
        raise RuntimeError(self.last_error)

    client = self._ensure_client()
    response = client.chat.completions.create(
        model=self.model,                   # deepseek-v4-flash
        messages=[
            {"role": "system", "content": system},   # 可选 system prompt
            {"role": "user",   "content": prompt},
        ],
        temperature=0.2,   # 低温度 → 意图分类和诊断需要确定性，不需要创意
        timeout=30,        # API 超时，与脚本执行超时（25s）独立
    )
    return response.choices[0].message.content or ""
```

| 参数 | 取值 | 选择原因 |
|---|---|---|
| `model` | `deepseek-v4-flash` | 速度快、成本低，适合意图分类任务 |
| `temperature` | 0.2 | 运维场景需要稳定、可复现的输出，不需要创意 |
| `timeout` | 30 秒 | 独立于脚本执行超时（25 秒），防止 API 挂起 |
| `messages` | system + user | system 定义角色约束，user 传递具体任务 |

### 2.4 报告总结接口

```python
def summarize_report(self, user_request: str, raw_output: str) -> str:
    system = (
        "你是 Linux 运维诊断助手。请根据命令输出写出简洁、可答辩展示的中文报告。"
        "报告必须包含：问题概述、关键证据、可能原因、建议处理步骤、"
        "涉及的 Linux 命令、风险提示。"
    )
    prompt = (
        f"用户请求：{user_request}\n\n"
        "以下是受控 Shell 脚本的输出，请生成诊断报告：\n"
        f"{raw_output[:12000]}"           # ← 截断保护：防止超 context window
    )
    return self.complete(prompt, system=system)
```

要求 DeepSeek 按六要素结构输出报告：**问题概述 → 关键证据 → 可能原因 → 建议处理步骤 → 涉及的 Linux 命令 → 风险提示**。

---

## 3. 数据层 — Skill 对象模型（skill_loader.py）

Planner 需要知道"有哪些 skill 可选"，这由 `skill_loader.py` 提供数据基础。

### 3.1 核心数据结构

```python
@dataclass(frozen=True)
class Skill:
    name: str                              # 如 "disk_check"
    description: str                       # 如 "检查磁盘空间、inode 使用率..."
    script: Path                           # 如 project_root / "scripts/disk_check.sh"
    risk_level: str                        # "low" / "medium" / "high"
    allowed_commands: tuple[str, ...]      # 如 ("df", "du", "find", "awk", "sort", "tail")
    keywords: tuple[str, ...]              # 如 ("disk", "df", "磁盘", "空间", "容量", ...)
    inputs: tuple[SkillInput, ...]         # 输入参数定义
```

### 3.2 关键词设计

每个 skill 的 YAML 文件中定义了中英文关键词，用于关键词降级匹配：

```yaml
# skills/disk_check.yaml
keywords:
  - disk          # 英文术语
  - df            # 命令名
  - du
  - inode
  - 磁盘          # 中文术语
  - 空间
  - 容量
  - 大文件
  - 日志满
```

加载后转为小写 tuple：`("disk", "df", "du", "inode", "磁盘", "空间", "容量", "大文件", "日志满")`

加载结果是一个以 skill name 为 key 的字典：

```python
skills = {
    "disk_check":     Skill(name="disk_check",     keywords=("disk","df",...),   ...),
    "log_analyze":    Skill(name="log_analyze",    keywords=("log","ssh",...),   ...),
    "process_check":  Skill(name="process_check",  keywords=("cpu","内存",...),  ...),
    "network_check":  Skill(name="network_check",  keywords=("网络","端口",...),  ...),
    "health_report":  Skill(name="health_report",  keywords=("巡检","daily",...),...),
}
```

---

## 4. 决策层 — Planner 意图路由器（planner.py）

### 4.1 决策结果数据结构

```python
@dataclass(frozen=True)
class Plan:
    skills: tuple[str, ...]       # 要执行的 skill 名称，如 ("disk_check",)
    reason: str                   # 选择原因
    refused: bool = False         # 是否被安全拦截
    refusal_reason: str = ""      # 拒绝原因
    source: str = "keyword"       # 来源标识：deepseek / keyword / safety / manual
    answer: str = ""              # 仅无 skill 时：DeepSeek 的普通回答文本
```

### 4.2 三段式路由 — plan() 主方法

```python
def plan(self, user_request: str, use_llm: bool = True) -> Plan:
    # ═══════════ 第一段：安全拦截 ═══════════
    if self._looks_dangerous(user_request):
        return Plan(skills=(), refused=True, source="safety", ...)

    # ═══════════ 第二段：LLM 智能路由 ═══════════
    if use_llm and self.llm_client and self.llm_client.available:
        llm_plan = self._plan_with_llm(user_request)
        if llm_plan:                        # 成功 → 返回
            return llm_plan                 # 返回 None → 降级

    # ═══════════ 第三段：关键词降级 ═══════════
    return self._plan_with_keywords(user_request)
```

三段之间是**严格的优先级链**：安全 > LLM > 关键词。上一段失败或不可用，自动降级到下一段。

---

## 5. 第一段：安全拦截

### 5.1 危险模式定义

```python
DANGEROUS_PATTERNS = (
    r"\brm\s+-rf\b",       # rm -rf、rm  -rf
    r"删除所有",
    r"清空",
    r"格式化",
    r"\bmkfs\b",           # mkfs.ext4、mkfs.xfs 等格式化命令
    r"\bshutdown\b",       # shutdown -h now
    r"\breboot\b",         # reboot -f
    r"重启服务器",
    r"关闭服务器",
)
```

### 5.2 匹配逻辑

```python
def _looks_dangerous(self, text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in DANGEROUS_PATTERNS)
```

### 5.3 为什么放在 LLM 调用之前？

| 原因 | 说明 |
|---|---|
| **确定性** | 正则匹配 100% 准确，不会误判或被绕过 |
| **零成本** | 不消耗 API 调用额度 |
| **防 prompt injection** | 用户输入中的恶意指令在到达 LLM 之前就被拦截 |
| **响应快** | 毫秒级判断，无需等待网络请求 |

---

## 6. 第二段：DeepSeek LLM 智能路由

### 6.1 整体流程

```
_plan_with_llm("检查磁盘空间问题")
  │
  ├── 步骤 1：构造 Skill 目录 JSON
  ├── 步骤 2：拼装 System Prompt
  ├── 步骤 3：调用 llm_client.complete(prompt)
  ├── 步骤 4：_parse_json_object(raw) — 三层容错解析
  └── 步骤 5：校验 + 过滤 + 构造 Plan
```

### 6.2 步骤 1：构造 Skill 目录

```python
skill_catalog = [
    {
        "name": skill.name,
        "description": skill.description,
        "risk_level": skill.risk_level,
        "keywords": list(skill.keywords),
    }
    for skill in self.skills.values()
]
```

**只提取 Planner 需要的 4 个字段**，不暴露 `script` 路径和 `allowed_commands`（最小权限原则）。

### 6.3 步骤 2：System Prompt 设计

```python
prompt = (
    # 角色定义
    "你是 Linux 运维 Agent 路由器。"
    "你只能从给定 skills 中选择 skill，禁止输出任意 Shell 命令。\n"

    # 触发条件约束
    "只有用户明确提出 Linux 运维诊断、巡检、日志、进程、网络、磁盘等需求时，"
    "才选择 skill。\n"

    # 无匹配处理
    "如果用户输入无意义内容、闲聊、普通知识问题，或者没有明确触发任何 skill，"
    "必须返回空 skills，并在 answer 字段中正常回答用户。"
    "不要为了有结果而默认选择 health_report。\n"

    # 输出格式约束
    "必须只返回 JSON，格式为："
    '{"skills":["disk_check"],"reason":"用户想检查磁盘空间","answer":""} '
    '或 {"skills":[],"reason":"未触发运维 skill","answer":"你的回答"}。\n'

    # 配置参数
    f"最多选择 {self.max_skills} 个 skill。\n"
    f"可用 skills: {json.dumps(skill_catalog, ensure_ascii=False)}\n"
    f"用户请求: {user_request}"
)
```

System Prompt 的五个关键约束：

| 约束 | 目的 | 防止的问题 |
|---|---|---|
| "禁止输出任意 Shell 命令" | 安全边界 | LLM 幻觉出危险命令 |
| "只有明确运维需求才选 skill" | 触发控制 | 闲聊被误诊断为运维操作 |
| "skills 为空时用 answer 回答" | 用户体验 | 无匹配时友好回复而非沉默 |
| "不要默认选择 health_report" | 防惰性匹配 | LLM 偷懒一律选综合巡检 |
| "必须只返回 JSON" | 结构化解析 | 自然语言无法可靠解析 |

### 6.4 步骤 3 + 4：调用 + JSON 解析

```python
raw = self.llm_client.complete(prompt)     # 调用 DeepSeek API
parsed = _parse_json_object(raw)           # 解析返回的 JSON
```

#### JSON 三层容错解析

```python
def _parse_json_object(text: str) -> dict:
    text = text.strip()

    # 容错 1：去除 Markdown 代码块标记
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    # 容错 2：定位 JSON 对象边界
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response does not contain a JSON object")

    # 容错 3：只解析 { } 之间的内容
    return json.loads(text[start : end + 1])
```

| LLM 实际输出 | 容错层级 | 处理结果 |
|---|---|---|
| ` ```json\n{"skills":["disk_check"]}\n``` ` | 容错 1 去代码块 | `{"skills":["disk_check"]}` |
| `好的，分析如下：\n{"skills":["disk_check"],"reason":"..."}\n以上` | 容错 2 提取 JSON | 成功解析 |
| `{"skills":["disk_check"]}` | 容错 3 直接解析 | 成功解析 |
| `抱歉，我无法处理这个请求` | 三层均失败 | ValueError → 返回 None，触发降级 |

### 6.5 步骤 5：校验 + 过滤 + 构造 Plan

```python
# 过滤：DeepSeek 返回的 skill 必须在 self.skills 中真实存在
selected = tuple(
    name
    for name in parsed.get("skills", [])
    if isinstance(name, str) and name in self.skills   # ← 防幻觉关键
)[: self.max_skills]                                  # 截断到最多 3 个

if selected:   # 有选中的 skill → 执行路径
    return Plan(
        skills=selected,
        reason=str(parsed.get("reason", "DeepSeek selected matching skills")),
        source="deepseek",
    )
else:          # 无 skill → 对话路径（不执行命令）
    return Plan(
        skills=(),
        reason=str(parsed.get("reason", "DeepSeek 未选择可执行 skill")),
        source="deepseek",
        answer=str(parsed.get("answer", "")).strip(),
    )
```

**防幻觉的关键代码**：`if name in self.skills`

即使 DeepSeek 返回 `{"skills":["delete_everything"]}`，因为这个名称不在真实 skill 字典中，会被直接丢弃，不会传递到 Executor 层。

### 6.6 异常处理

整个 `_plan_with_llm` 被 `try/except Exception` 包裹：

```python
try:
    raw = self.llm_client.complete(prompt)
    # ... 解析、过滤、构造 Plan
except Exception:
    return None   # 任何异常 → 返回 None → 触发降级到关键词模式
```

降级触发条件包括：网络错误、API 超时、JSON 解析失败、API Key 无效。

---

## 7. 第三段：关键词匹配降级

纯本地、零外部依赖的确定性路由：

```python
def _plan_with_keywords(self, user_request: str) -> Plan:
    lowered = user_request.lower()
    scores: list[tuple[int, str]] = []

    for skill in self.skills.values():
        score = 0

        # 来源 1：关键词匹配（权重 +2）
        for keyword in skill.keywords:
            if keyword and _keyword_matches(keyword, lowered):
                score += 2

        # 来源 2：skill name 中的 token（权重 +1）
        for token in re.split(r"\W+", skill.name.lower()):
            if token and token in lowered:
                score += 1

        if score:
            scores.append((score, skill.name))

    if not scores:
        return Plan(skills=(), reason="未命中明确关键词，不执行任何 skill", source="keyword")

    selected = tuple(name for _, name in sorted(scores, reverse=True)[:self.max_skills])
    return Plan(skills=selected, reason="本地关键词匹配选择 skill", source="keyword")
```

### 7.1 关键词匹配的智能边界检测

```python
def _keyword_matches(keyword: str, text: str) -> bool:
    # Case 1：纯 ASCII 字母数字关键词
    if keyword.isascii() and re.fullmatch(r"[a-z0-9_+-]+", keyword):
        if len(keyword) <= 3:    # 短词（df, du, ps, ss, ip）→ 必须整词匹配
            return re.search(
                rf"(?<![a-z0-9_+-]){re.escape(keyword)}(?![a-z0-9_+-])",
                text
            ) is not None
        return keyword in text    # 长词（disk, network, journalctl）→ 子串匹配

    # Case 2：含中文或特殊字符 → 直接子串匹配
    return keyword in text
```

**短词整词匹配的设计原因**：防止误触发。

| 用户输入 | 短词 | 是否匹配 | 原因 |
|---|---|---|---|
| `display settings` | `ps` | ❌ 不匹配 | `ps` 在 `display` 内部，不是独立词 |
| `check ps aux` | `ps` | ✅ 匹配 | `ps` 是独立 token |
| `network slow` | `ip` | ❌ 不匹配 | 短词需整词边界 |

---

## 8. 对接全景：一次请求的完整调用链

以"检查磁盘空间问题"为例，追踪 Planner 和 DeepSeek 的协作过程：

```
main.py
  │
  ├── 1. 配置加载
  │     config = load_config()
  │     └── DeepSeekConfig(base_url="https://api.deepseek.com",
  │                        model="deepseek-v4-flash", timeout=30)
  │
  ├── 2. Skill 加载
  │     skills = load_skills()
  │     └── {"disk_check": Skill(keywords=("磁盘","空间",...)),
  │           "log_analyze": Skill(keywords=("ssh","日志",...)),
  │           ... }
  │
  ├── 3. LLM 客户端初始化
  │     llm_client = DeepSeekClient(config.deepseek)
  │     ├── 第 1 层：python-dotenv 加载 .env
  │     ├── 第 2 层：手动解析兜底
  │     └── 第 3 层：修复 SOCKS 代理冲突
  │
  ├── 4. Planner 初始化
  │     planner = Planner(skills, llm_client=llm_client, max_skills=3)
  │
  ├── 5. 意图路由
  │     plan = planner.plan("检查磁盘空间问题")
  │       │
  │       ├── 第一段：_looks_dangerous("检查磁盘空间问题")
  │       │     └── 无危险词 → 放行
  │       │
  │       ├── 第二段：_plan_with_llm("检查磁盘空间问题")
  │       │   │
  │       │   ├── 构造 skill_catalog JSON（5 个 skill 的 name/desc/keywords）
  │       │   │
  │       │   ├── 拼装 System Prompt：
  │       │   │   "你是 Linux 运维 Agent 路由器。你只能从给定 skills 中选择 skill，
  │       │   │    禁止输出任意 Shell 命令。必须只返回 JSON..."
  │       │   │
  │       │   ├── llm_client.complete(prompt)
  │       │   │     └── OpenAI SDK → POST https://api.deepseek.com/v1/chat/completions
  │       │   │           Headers: {Authorization: Bearer sk-xxx}
  │       │   │           Body: {
  │       │   │             model: "deepseek-v4-flash",
  │       │   │             messages: [{role: "user", content: prompt}],
  │       │   │             temperature: 0.2,
  │       │   │             timeout: 30
  │       │   │           }
  │       │   │           ← Response: {
  │       │   │               choices: [{
  │       │   │                 message: {
  │       │   │                   content: '{"skills":["disk_check"],
  │       │   │                              "reason":"用户想检查磁盘空间使用情况",
  │       │   │                              "answer":""}'
  │       │   │                 }
  │       │   │               }]
  │       │   │             }
  │       │   │
  │       │   ├── _parse_json_object(raw)
  │       │   │     原始: '{"skills":["disk_check"],"reason":"...","answer":""}'
  │       │   │     → json.loads → {"skills":["disk_check"], "reason":"...", "answer":""}
  │       │   │
  │       │   ├── 过滤校验
  │       │   │     DeepSeek 返回: ["disk_check"]
  │       │   │     self.skills 中: {"disk_check","log_analyze","process_check",...}
  │       │   │     交集: ["disk_check"] ✓   （若是幻觉 skill → 被丢弃）
  │       │   │     截断: ["disk_check"]     （若 >3 个 → 只取前 3）
  │       │   │
  │       │   └── return Plan(
  │       │           skills=("disk_check",),
  │       │           reason="用户想检查磁盘空间使用情况",
  │       │           source="deepseek"
  │       │       )
  │       │
  │       └── 第三段：跳过（第二段已返回结果）
  │
  └── 6. 输出
        print(f"请求：检查磁盘空间问题")
        print(f"选择方式：deepseek")
        print(f"选择原因：用户想检查磁盘空间使用情况")
        print(f"执行 skills：disk_check")
```

---

## 9. 降级路径全景（容错设计）

```
                    Planner 输入
                         │
          ┌──────────────▼──────────────┐
          │ _looks_dangerous() 危险检查   │
          │  命中 → refused=true, 终止    │
          └──────────────┬──────────────┘
                         │ 未命中
          ┌──────────────▼──────────────┐
          │ use_llm=True                 │
          │ 且 llm_client 不为 None       │
          │ 且 llm_client.available      │── 任一为 False ──┐
          └──────────────┬──────────────┘                   │
                         │ 全部为 True                       │
          ┌──────────────▼──────────────┐                   │
          │ _plan_with_llm()            │                   │
          │  ├─ API 调用                │                   │
          │  ├─ JSON 解析               │                   │
          │  └─ Skill 过滤              │                   │
          └──────────────┬──────────────┘                   │
                         │                                  │
              ┌──────────┼──────────┐                       │
              │          │          │                       │
          返回 Plan   返回 None  抛异常                      │
          (成功)    (LLM 判无)  (网络/解析/超时)              │
              │          │          │                       │
              │          └──────────┼───────────────────────┘
              │                     │
              │          ┌──────────▼──────────┐
              │          │ _plan_with_keywords()│  ← 降级终点
              │          │  纯本地，确定性路由     │
              │          └──────────┬──────────┘
              │                     │
              │        ┌────────────┼────────────┐
              │        │            │            │
              │    有命中 skill  无命中 skill     │
              │        │            │            │
              │   Plan(skills=   Plan(skills=())  │
              │   ("disk_check",))  source=keyword │
              │        │            │            │
              └────────┴────────────┴────────────┘
```

---

## 10. 关键设计决策总结

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| 1 | API 调用方式 | OpenAI 兼容 SDK | DeepSeek 兼容 OpenAI 协议，可随时切换模型 |
| 2 | Temperature | 0.2 | 运维意图分类和诊断需要确定性，不需要创意 |
| 3 | API 超时 | 30 秒 | 与脚本执行超时（25 秒）独立，各有边界 |
| 4 | JSON 解析 | 宽松三层容错 | LLM 输出不可控，需容忍各种格式偏差 |
| 5 | LLM 输出校验 | `name in self.skills` | 防止 LLM 幻觉出虚构 skill |
| 6 | 危险拦截时机 | LLM 调用之前 | 正则 100% 确定，零成本，防 prompt injection |
| 7 | 降级策略 | 安全→LLM→关键词 | 核心诊断功能不依赖外部 API |
| 8 | 环境加载 | 三层（库→手动→代理） | 每层独立容错，纵深防御 |
| 9 | OpenAI Client | 延迟初始化 | `--no-llm` 和 `doctor` 模式不触发 import |
| 10 | Skill 目录 | 只暴露 name/desc/keywords/risk | 不暴露脚本路径，最小权限原则 |
