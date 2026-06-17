# Linux Ops Agent

基于 DeepSeek 的 Linux 运维诊断 Agent Skills 课程项目。

项目目标不是让大模型直接控制系统，而是让大模型选择预先登记的运维 skill，再由本地程序安全执行受控 Shell 脚本，最后把命令输出整理成诊断报告。

## 功能

- 磁盘空间和 inode 检查
- 系统日志和 SSH 登录失败分析
- CPU、内存和进程状态检查
- 网络监听端口和连通性检查
- 一键生成系统巡检报告
- DeepSeek 意图识别和报告总结
- DeepSeek 不可用时自动退化为关键词匹配

## 技术点

- Bash 脚本
- Linux 命令
- grep/sed/awk 文本处理
- 管道与重定向
- 日志分析
- 进程管理
- Python 调用 Linux 功能
- Agent Skills
- Git 代码管理

## 安装

```bash
cd linux-ops-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，填入 DeepSeek API Key：

```text
DEEPSEEK_API_KEY=你的key
```

没有 API Key 也可以运行，系统会自动使用本地关键词匹配模式。

## 运行

推荐使用便捷入口：

```bash
./ops
```

进入交互模式后直接输入中文问题，不需要引号：

```text
ops> 检查磁盘空间问题
ops> 分析最近 SSH 登录失败
ops> daily
ops> exit
```

也可以单次运行：

```bash
./ops 检查磁盘空间问题
```

查看 skills：

```bash
python main.py --list-skills
```

按自然语言执行诊断：

```bash
python main.py "检查磁盘空间问题"
python main.py "分析最近 SSH 登录失败"
python main.py "生成今日服务器巡检报告"
```

直接执行指定 skill：

```bash
python main.py --skill disk_check
python main.py --skill log_analyze
python main.py --report daily
```

报告会保存到 `reports/` 目录。

## 测试

```bash
python3 -m unittest discover -s tests
bash scripts/disk_check.sh
bash scripts/log_analyze.sh
python main.py --list-skills
python main.py --skill disk_check --no-llm
```

如果已经安装 `pytest`，也可以直接运行：

```bash
pytest
```

## 安全设计

- 程序只执行 `skills/*.yaml` 中登记的脚本。
- 不接受大模型返回的任意 Shell 命令。
- 默认拒绝高风险和破坏性命令。
- 每次脚本执行都有超时限制。
- 命令输出会保存为 Markdown 报告，方便答辩展示。
