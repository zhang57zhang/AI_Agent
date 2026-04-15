# OpenCode Agent

OpenCode 风格的 AI 编码助手 — 终端 TUI，支持 MCP、LSP、多 Agent 编排，可对接多种 LLM 后端。

## 功能特性

- **多 LLM 后端**：OpenAI / Anthropic / Ollama / OpenRouter / 任意 OpenAI 兼容接口
- **Ollama 远程连接**：通过 IP 地址连接局域网或服务器部署的 Ollama
- **全功能工具集**：文件读写、Bash 执行、Git 操作、Web 搜索、MCP 动态发现
- **Agent Loop**：流式输出、工具调用链、最多 25 轮自动迭代
- **会话持久化**：SQLite 存储对话历史，支持多会话管理
- **终端 TUI**：基于 Textual 的 Rich 终端界面，Flexoki 暗色主题
- **安全控制**：危险命令拦截、权限系统、工具审批机制
- **技能系统**：Markdown 格式的技能文件，可热加载

## 环境要求

- **Python** >= 3.12
- **操作系统**：Windows / macOS / Linux
- **LLM 账号**（至少配置一种）：
  - OpenAI（`sk-...`）
  - Anthropic（`sk-ant-...`）
  - Ollama（本地或远程服务器）

## 安装

```bash
# 克隆仓库
git clone git@github.com:zhang57zhang/AI_Agent.git
cd AI_Agent

# 创建虚拟环境（推荐 uv，也可用 venv）
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 安装依赖
pip install -e ".[dev]"
```

## 快速开始

### 1. 配置 API Key

创建 `.env` 文件（或设置环境变量）：

```bash
# OpenAI
OPENCODE_PROVIDERS__OPENAI__API_KEY=sk-your-openai-key

# Anthropic
OPENCODE_PROVIDERS__ANTHROPIC__API_KEY=sk-ant-your-key

# OpenRouter
OPENCODE_PROVIDERS__OPENROUTER__API_KEY=sk-or-your-key
```

> 环境变量前缀为 `OPENCODE_`，使用双下划线 `__` 表示嵌套。

### 2. 启动

```bash
# 使用 OpenAI（默认）
opencode-agent

# 指定模型
opencode-agent --model gpt-4o

# 使用 Anthropic
opencode-agent --provider anthropic --model claude-sonnet-4-20250514

# 使用本地 Ollama
opencode-agent --provider ollama --model qwen2:7b

# 连接远程 Ollama（通过 IP）
opencode-agent --ollama-url http://192.168.1.100:11434 --model llama3

# 使用 OpenRouter
opencode-agent --provider openrouter --model google/gemini-2.0-flash-exp:free
```

### 3. 在 TUI 中操作

启动后进入终端界面，直接输入你的问题或指令，Agent 会自动调用工具完成。

## CLI 参数

| 参数 | 简写 | 说明 |
|------|------|------|
| `--model` | `-m` | 指定模型（如 `gpt-4o`, `qwen2:7b`, `llama3`） |
| `--provider` | `-p` | LLM 提供商：`openai` / `anthropic` / `ollama` / `local` / `openrouter` |
| `--ollama-url` | | Ollama 服务器地址，自动设置 `--provider ollama` |
| `--agent` | `-a` | Agent 类型：`coder`（默认）/ `task` / `summarizer` / `title` |
| `--working-dir` | `-w` | 工作目录（默认当前目录） |
| `--prompt` | `-P` | 自定义 SYSTEM_PROMPT.md 路径 |
| `--skills-dir` | `-s` | 技能文件目录 |
| `--no-mcp` | | 禁用 MCP 工具发现 |
| `--no-lsp` | | 禁用 LSP 集成 |
| `--debug` | | 启用调试日志 |
| `--version` | `-v` | 显示版本号 |

## Ollama 使用指南

### 本地 Ollama

```bash
# 确保 Ollama 已运行
ollama serve

# 启动 Agent
opencode-agent --provider ollama --model qwen2:7b
```

### 远程 Ollama（IP 连接）

适用于局域网或服务器上部署的 Ollama：

```bash
# 连接指定 IP 的 Ollama
opencode-agent --ollama-url http://192.168.1.100:11434 --model qwen2:7b

# 使用自定义端口
opencode-agent --ollama-url http://10.0.0.5:8080 --model llama3
```

### Ollama 配置项

通过环境变量或 `.env` 文件配置：

```bash
# Ollama 服务器地址
OPENCODE_PROVIDERS__OLLAMA__HOST=192.168.1.100
OPENCODE_PROVIDERS__OLLAMA__PORT=11434
OPENCODE_PROVIDERS__OLLAMA__BASE_URL=http://192.168.1.100:11434/v1
```

### Ollama 管理 API

`OllamaProvider` 额外提供管理接口（编程调用时可用）：

```python
from opencode_agent.provider.ollama_provider import OllamaProvider

provider = OllamaProvider(host="192.168.1.100", port=11434, model="qwen2:7b")

# 检查服务健康状态
info = await provider.health_check()
print(info)  # {"version": "0.5.4", ...}

# 列出可用模型
models = await provider.list_models()
for m in models:
    print(m["name"], m["size"])

# 查看模型详情
details = await provider.model_info("qwen2:7b")

# 拉取新模型
async for status in provider.pull_model("codellama:13b"):
    print(status)
```

## 环境变量参考

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENCODE_DEFAULT_PROVIDER` | 默认 LLM 提供商 | `openai` |
| `OPENCODE_PROVIDERS__OPENAI__API_KEY` | OpenAI API Key | |
| `OPENCODE_PROVIDERS__ANTHROPIC__API_KEY` | Anthropic API Key | |
| `OPENCODE_PROVIDERS__OLLAMA__HOST` | Ollama 主机 | `localhost` |
| `OPENCODE_PROVIDERS__OLLAMA__PORT` | Ollama 端口 | `11434` |
| `OPENCODE_PROVIDERS__OLLAMA__BASE_URL` | Ollama API 地址 | `http://localhost:11434/v1` |
| `OPENCODE_PROVIDERS__LOCAL__BASE_URL` | 本地兼容端点 | `http://localhost:11434/v1` |
| `OPENCODE_PROVIDERS__OPENROUTER__API_KEY` | OpenRouter API Key | |
| `OPENCODE_SYSTEM_PROMPT_PATH` | 系统提示词路径 | `SYSTEM_PROMPT.md` |
| `OPENCODE_SKILLS_DIR` | 技能文件目录 | `skills` |
| `OPENCODE_DATA_DIR` | 数据目录 | `~/.opencode_agent` |
| `OPENCODE_SESSIONS_DB` | 会话数据库路径 | `{data_dir}/sessions.db` |
| `OPENCODE_ENABLE_LSP` | 启用 LSP | `true` |
| `OPENCODE_ENABLE_MCP` | 启用 MCP | `true` |
| `OPENCODE_ENABLE_GIT` | 启用 Git | `true` |

## 项目结构

```
AI_Agent/
├── pyproject.toml                  # 项目配置与依赖
├── SYSTEM_PROMPT.md                # 系统提示词（377 行，10 节）
├── README.md                       # 本文件
├── .gitignore
├── opencode_agent/                 # 主包
│   ├── __init__.py                 # v0.1.0
│   ├── cli.py                      # CLI 入口（argparse）
│   ├── config.py                   # pydantic-settings 配置管理
│   ├── base_types.py               # 数据模型（Message, Session, AgentEvent 等）
│   ├── pubsub.py                   # 事件总线
│   ├── permissions.py              # 权限系统
│   ├── agent/
│   │   ├── loop.py                 # Agent Loop 核心（流式、工具链、25 轮限制）
│   │   ├── prompt.py               # 提示词引擎（SYSTEM_PROMPT + 技能加载）
│   │   └── session.py              # 会话管理（SQLite 持久化）
│   ├── provider/
│   │   ├── __init__.py             # Provider 工厂
│   │   ├── base.py                 # 抽象 Provider 接口
│   │   ├── openai_provider.py      # OpenAI / 兼容接口
│   │   ├── anthropic_provider.py   # Anthropic Claude
│   │   └── ollama_provider.py      # Ollama 本地/远程（含管理 API）
│   ├── tools/
│   │   ├── __init__.py             # 工具注册中心
│   │   ├── base.py                 # BaseTool 抽象接口
│   │   ├── file_tools.py           # 6 个文件工具（read/write/edit/glob/grep/ls）
│   │   ├── bash_tool.py            # Shell 执行（超时、危险命令拦截）
│   │   ├── web_tools.py            # Web 抓取 + 搜索
│   │   ├── git_tools.py            # 6 个 Git 工具
│   │   └── mcp_tools.py            # MCP 动态发现
│   └── tui/
│       ├── app.py                  # Textual TUI 主应用
│       ├── components/             # TUI 组件
│       └── styles/                 # Flexoki 暗色主题
├── tests/
│   └── test_e2e.py                 # E2E 测试（30 个用例，无 mock）
├── skills/                         # 技能 Markdown 文件目录
└── sections/                       # 提示词分段参考
```

## 内置工具

### 文件工具
| 工具 | 说明 |
|------|------|
| `read_file` | 读取文件内容，支持分页 |
| `write_file` | 写入文件，自动创建父目录 |
| `edit_file` | 精确替换文件中的文本片段 |
| `glob` | 按模式匹配文件路径 |
| `grep` | 正则搜索文件内容 |
| `list_directory` | 列出目录内容 |

### Bash 工具
| 工具 | 说明 |
|------|------|
| `bash_command` | 执行 Shell 命令，支持超时控制，自动拦截危险命令（`rm -rf /` 等） |

### Web 工具
| 工具 | 说明 |
|------|------|
| `web_fetch` | 抓取 URL 内容（返回 Markdown） |
| `web_search` | Web 搜索 |

### Git 工具
| 工具 | 说明 |
|------|------|
| `git_status` | 查看 Git 状态 |
| `git_diff` | 查看差异 |
| `git_log` | 查看提交历史 |
| `git_add` | 暂存文件 |
| `git_commit` | 提交变更 |
| `git_branch` | 分支管理 |

### MCP 工具
通过 MCP 协议动态发现和加载外部工具服务器。

## 测试

```bash
# 运行全部 E2E 测试（30 个用例，无 mock，需要真实 LLM 连接）
pytest tests/test_e2e.py -v

# 运行单个测试类别
pytest tests/test_e2e.py -v -k "TestT9"     # 仅 Ollama 测试
pytest tests/test_e2e.py -v -k "TestT1"     # 仅文件工具测试

# 带超时运行
pytest tests/test_e2e.py -v --timeout=120

# 调试模式
opencode-agent --debug
```

### 测试矩阵

| 类别 | 数量 | 说明 |
|------|------|------|
| T1 文件工具 | 6 | 读取、写入、编辑、搜索 |
| T2 Bash 工具 | 3 | 正常执行、超时、危险命令拦截 |
| T3 Web 工具 | 2 | HTTP 抓取、Web 搜索 |
| T4 Git 工具 | 2 | 非 Git 目录、项目目录 |
| T5 Provider | 3 | 流式文本、工具调用、非流式 |
| T6 提示词引擎 | 3 | 系统提示词加载、Agent 前缀、工具描述 |
| T7 Agent Loop | 3 | 简单对话、工具调用链、多轮记忆 |
| T8 会话持久化 | 3 | CRUD 生命周期、消息持久化、排序 |
| T9 Ollama | 5 | 构造、地址规范化、配置枚举、工厂、健康检查 |

## 开发

### 代码风格

```bash
# Lint
ruff check .

# 格式化
ruff format .

# 类型检查
mypy opencode_agent/
```

### 添加新 Provider

1. 在 `config.py` 的 `ModelProvider` 枚举中添加新值
2. 在 `provider/` 下创建新的 Provider 文件，继承 `BaseProvider`
3. 在 `provider/__init__.py` 的 `create_provider()` 工厂中注册
4. 在 `cli.py` 的 `--provider` 参数中自动生效（基于枚举）

### 添加新工具

1. 在 `tools/` 下创建新文件，继承 `BaseTool`
2. 实现 `name`、`description`、`parameters`、`run()` 方法
3. 在 `tools/__init__.py` 的工具集中注册

## License

MIT