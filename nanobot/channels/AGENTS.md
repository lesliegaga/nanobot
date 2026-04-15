# CHANNELS 模块

## 概览
聊天平台集成 —— 10+ 个频道统一接入消息总线。

## 约束
- **所有回复必须使用中文**。

## 目录结构
```
channels/
├── base.py           # BaseChannel 抽象基类
├── manager.py        # ChannelManager —— 生命周期管理 + 出站分发
├── telegram.py
├── discord.py
├── whatsapp.py
├── feishu.py
├── mochat.py
├── dingtalk.py
├── email.py
├── slack.py
├── qq.py
└── matrix.py
```

## 按任务定位代码
| 任务 | 位置 | 说明 |
|------|----------|-------|
| 添加频道 | `channels/manager.py` + `channels/base.py` | 继承 `BaseChannel`，然后在 manager 中导入 |
| 修改权限逻辑 | `channels/base.py` | `is_allowed()` —— 空列表拒绝全部，`"*"` 允许全部 |
| 修改出站路由 | `channels/manager.py` | `_dispatch_outbound()` 从总线读取并发送 |
| Telegram 细节 | `channels/telegram.py` | 支持通过 Groq 进行语音转录 |
| WhatsApp 细节 | `channels/whatsapp.py` | 需要 Node.js 桥接层 |
| Matrix 细节 | `channels/matrix.py` | 通过 matrix-nio 支持 E2EE |

## 约定
- 每个频道都继承 `BaseChannel`，并实现 `start()`、`stop()`、`send()`。
- 收到消息后必须调用 `_handle_message()`，该方法会在发布到总线前检查 `is_allowed()`。
- `group_policy` 选项：`"mention"` | `"open"` | `"allowlist"`（因频道而异）。
- 自 `v0.1.4.post4` 起，空的 `allow_from` 会在启动时抛出错误。

## 独特风格
- WhatsApp 是**唯一**使用 Node.js 桥接层（`bridge/`）的频道，其余均为纯 Python 实现。
- 飞书、钉钉、QQ 和 Mochat 使用 WebSocket / Stream 模式 —— 无需公网 IP。
