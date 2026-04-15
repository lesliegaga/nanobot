# WHATSAPP 桥接层

## 概览
TypeScript/Node.js WebSocket 桥接层 —— nanobot 中唯一非 Python 的组件。

## 约束
- **所有回复必须使用中文**。

## 目录结构
```
bridge/
├── package.json
├── tsconfig.json
└── src/
    ├── index.ts      # 入口
    ├── server.ts     # WebSocket 服务器
    ├── whatsapp.ts   # WhatsApp 客户端逻辑
    └── types.d.ts    # 类型定义
```

## 按任务定位代码
| 任务 | 位置 | 说明 |
|------|----------|-------|
| 桥接层启动 | `src/index.ts` | 创建服务器，连接 WhatsApp |
| WebSocket 服务器 | `src/server.ts` | 处理 Python ↔ 桥接层通信 |
| WhatsApp 客户端 | `src/whatsapp.ts` | WhatsApp Web 逻辑 |
| 依赖管理 | `package.json` | 需要 Node.js 20+ |

## 约定
- 通过 `npm install && npm run build` 构建。
- Docker 镜像在同一容器内构建桥接层（非多阶段构建）。
- 本地桥接层缓存在 `~/.nanobot/bridge`。

## 反模式
- 永远不要使用 `as any`、`@ts-ignore` 或 `@ts-expect-error`。
- 不要认为桥接层会在 nanobot 升级时自动更新 —— 升级后需手动重建：`rm -rf ~/.nanobot/bridge && nanobot channels login`。
