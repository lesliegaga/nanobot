# 项目知识库

**生成时间：** 2026-04-15  
**提交：** 1d7fc8f  
**分支：** main

## 约束
- **所有回复必须使用中文**。

## 概览
nanobot 是一款超轻量级个人 AI 助手框架。核心技术栈：Python 3.11+（agent、channels、providers）+ 用于 WhatsApp 的 TypeScript/Node.js 桥接层。

## 目录结构
```
nanobot/
├── agent/          # 核心 agent 循环、工具、记忆、技能、子代理
├── channels/       # 聊天平台集成（10+ 平台）
├── providers/      # 大模型提供商注册表与实现
├── bus/            # 异步消息路由（入站/出站队列）
├── config/         # Pydantic 配置模式与加载
├── cron/           # 定时任务服务
├── heartbeat/      # 周期性唤醒服务
├── session/        # 对话会话管理
├── skills/         # 内置 agent 技能（基于 Markdown）
├── templates/      # 提示词/记忆模板
├── cli/            # Typer 命令行入口
└── utils/          # 公共辅助函数
bridge/             # TypeScript WhatsApp 桥接层（Node.js）
tests/              # pytest-asyncio 测试套件
```

## 按任务定位代码
| 任务 | 位置 | 说明 |
|------|----------|-------|
| 添加 LLM 提供商 | `nanobot/providers/registry.py` + `nanobot/config/schema.py` | 只需两步的注册表模式 |
| 添加聊天频道 | `nanobot/channels/` + `nanobot/channels/manager.py` | 继承 `BaseChannel` |
| 添加 agent 工具 | `nanobot/agent/tools/` | 继承 `Tool` 基类 |
| 修改 CLI 命令 | `nanobot/cli/commands.py` | Typer 入口 |
| 修改配置模式 | `nanobot/config/schema.py` | Pydantic `Base` 模型 |
| WhatsApp 桥接层 | `bridge/src/` | 仅 TypeScript/Node.js |
| 测试模式 | `tests/` | pytest-asyncio，auto 模式 |

## 代码地图
| 符号 | 类型 | 位置 | 作用 |
|--------|------|----------|------|
| AgentLoop | class | `nanobot/agent/loop.py` | 核心处理引擎 |
| ToolRegistry | class | `nanobot/agent/tools/registry.py` | 动态工具注册 |
| ContextBuilder | class | `nanobot/agent/context.py` | 提示词组装 |
| MessageBus | class | `nanobot/bus/queue.py` | 频道与 agent 解耦 |
| ChannelManager | class | `nanobot/channels/manager.py` | 频道生命周期管理 |
| ProviderSpec | dataclass | `nanobot/providers/registry.py` | 提供商元数据 |
| SkillsLoader | class | `nanobot/agent/skills.py` | 技能发现与加载 |

## 约定
- **Ruff**：行长度 100，目标 `py311`，忽略 `E501`。
- **配置键**：`Base` 模型通过 `to_camel` 别名生成器同时接受 `camelCase` 和 `snake_case`。
- **工具返回值**：所有工具返回 `str`。在 `ToolRegistry.execute` 中，以 `"Error"` 开头的错误会追加 `_HINT` 后缀。
- **频道白名单**：自 `v0.1.4.post4` 起，空的 `allow_from` 默认拒绝所有访问。使用 `["*"]` 可允许所有人。
- **添加提供商**：仅需两步 —— 在 `registry.py` 添加 `ProviderSpec`，在 `schema.py` 的 `ProvidersConfig` 中添加字段。
- **技能**：Markdown 文件（`SKILL.md`），带 YAML frontmatter。工作区技能优先于内置技能。
- **MCP 配置**：兼容 Claude Desktop / Cursor 格式（`command`+`args` 或 `url`+`headers`）。

## 反模式（本项目）
- **不要**把提醒事项写到 `MEMORY.md` —— 那样不会触发实际通知。
- **不要**通过 `exec` 调用 `nanobot cron` —— 请使用内置的 `cron` 工具。
- 在 TypeScript 中永远不要使用 `as any`、`@ts-ignore` 或 `@ts-expect-error`。
- 不要通过删除失败的测试来让其"通过"。

## 独特风格
- **多实例**：运行时会根据 `--config` 路径推导工作区/配置目录。每个实例通过独立的配置目录实现隔离。
- **桥接层混合架构**：WhatsApp 是唯一需要 Node.js 桥接层（`bridge/`）的频道，其余频道均为纯 Python 实现。
- **注册表驱动提供商**：没有 if-elif 链 —— `ProviderSpec` 统一管理环境变量、模型前缀和状态展示。
- **通过虚拟工具调用实现心跳**：`HeartbeatService` 使用强制的 `heartbeat` 工具调用来决定是否执行周期性任务。

## 常用命令
```bash
# 开发
pip install -e .
ruff check .

# 测试
pytest

# 运行
nanobot onboard          # 初始化配置与工作区
nanobot agent            # 交互式 CLI
nanobot gateway          # 启动聊天网关
nanobot status           # 查看状态
```

## 注意事项
- WhatsApp 桥接层不会在升级时自动更新。升级后请执行：`rm -rf ~/.nanobot/bridge && nanobot channels login`
- 设置 `restrictToWorkspace: true` 可将所有文件/壳命令工具限制在工作区目录内。
- 桥接层在 Docker 镜像内部构建（Node + Python 单镜像，非多阶段构建）。
