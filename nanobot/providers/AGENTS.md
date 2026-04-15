# PROVIDERS 模块

## 概览
大模型提供商注册表与实现。没有 if-elif 链 —— 一切皆由 `ProviderSpec` 驱动。

## 约束
- **所有回复必须使用中文**。

## 目录结构
```
providers/
├── registry.py               # ProviderSpec 数据类 + PROVIDERS 元组
├── base.py                   # LLMProvider 抽象基类
├── litellm_provider.py       # 通用 LiteLLM 包装器
├── custom_provider.py        # 直连 OpenAI 兼容端点
├── azure_openai_provider.py  # Azure 直连调用
├── openai_codex_provider.py  # 基于 OAuth 的 Codex 提供商
└── transcription.py          # Groq Whisper 语音转录
```

## 按任务定位代码
| 任务 | 位置 | 说明 |
|------|----------|-------|
| 添加提供商 | `providers/registry.py` + `config/schema.py` | 第一步：添加 `ProviderSpec`；第二步：添加配置字段 |
| 修改环境变量逻辑 | `providers/registry.py` | `env_key`、`env_extras`，支持 `{api_key}` / `{api_base}` 占位符 |
| 修改模型前缀逻辑 | `providers/registry.py` | `litellm_prefix`、`skip_prefixes`、`strip_model_prefix` |
| 直连（非 LiteLLM）提供商 | `providers/custom_provider.py` | `is_direct=True` 绕过 LiteLLM |
| OAuth 提供商 | `providers/openai_codex_provider.py` | `is_oauth=True` |

## 约定
- **仅需两步添加**：`registry.py` + `schema.py`。其余（环境变量、前缀、状态展示）均自动从规范推导。
- `PROVIDERS` 元组中的顺序 = 匹配优先级。
- 网关型提供商（`is_gateway=True`）可路由任意模型，在 fallback 中优先匹配。
- `detect_by_key_prefix` / `detect_by_base_keyword` 可在未显式指定提供商名时自动选择。

## 反模式
- 不要在注册表之外添加手动的 if-elif 提供商选择逻辑。
