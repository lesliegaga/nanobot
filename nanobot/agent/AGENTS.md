# AGENT 模块

## 概览
核心 agent 引擎：循环、上下文构建器、记忆、技能、子代理与工具注册表。

## 约束
- **所有回复必须使用中文**。

## 目录结构
```
agent/
├── loop.py           # AgentLoop —— LLM ↔ 工具执行循环
├── context.py        # ContextBuilder —— 提示词组装
├── memory.py         # MemoryStore —— 持久化回忆
├── skills.py         # SkillsLoader —— Markdown 技能发现
├── subagent.py       # SubagentManager —— 后台任务执行
└── tools/
    ├── base.py       # Tool 抽象基类
    ├── registry.py   # ToolRegistry —— 动态注册
    ├── shell.py      # ExecTool
    ├── filesystem.py # 读/写/编辑/列表工具
    ├── web.py        # WebSearch / WebFetch
    ├── message.py    # MessageTool
    ├── spawn.py      # SpawnTool（子代理调度）
    ├── cron.py       # CronTool
    └── mcp.py        # MCP 服务器工具
```

## 按任务定位代码
| 任务 | 位置 | 说明 |
|------|----------|-------|
| 添加工具 | `agent/tools/` | 继承 `Tool`，然后在 `AgentLoop.__init__` 中注册 |
| 修改工具执行 | `agent/tools/registry.py` | 参数类型转换、模式校验、错误追加 `_HINT` |
| 修改提示词组装 | `agent/context.py` | 构建 system + 历史 + 记忆 + 技能 |
| 修改记忆逻辑 | `agent/memory.py` | 合并与检索逻辑 |
| 修改技能加载行为 | `agent/skills.py` | 工作区技能覆盖内置技能 |
| 启动子代理 | `agent/subagent.py` | 使用相同提供商运行后台任务 |

## 约定
- 所有工具返回 `str`，非字符串结果会被强制转换。
- `ToolRegistry.execute` 会按模式转换参数、校验后再执行。以 `"Error"` 开头的错误会追加 `_HINT` 后缀。
- Agent 默认值：`max_iterations=40`、`temperature=0.1`、`max_tokens=4096`。
- 技能是带 YAML frontmatter 的 `SKILL.md` Markdown 文件。

## 反模式
- **不要**从工具中把提醒事项写到 `MEMORY.md` —— 那样不会触发通知。
- **不要**通过 `exec` 调用 `nanobot cron` —— 请使用 `cron` 工具。
