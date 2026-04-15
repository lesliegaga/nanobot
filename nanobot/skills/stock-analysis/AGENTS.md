# STOCK-ANALYSIS 技能

## 概览
内置金融分析技能，包含约 3,300+ 行指标逻辑，并通过 JNI 桥接 Java/原生库。

## 约束
- **所有回复必须使用中文**。

## 目录结构
```
stock-analysis/
├── indicators/
│   ├── __init__.py       # 导出 compute_all_indicators、compute_advanced_indicators
│   ├── signals.py        # 2,200+ 行 —— 信号生成
│   ├── libformula.py     # 800+ 行 —— 公式引擎
│   └── ta.py             # 技术分析封装
├── scripts/
│   ├── cli.py
│   ├── run_ab_indicators_check.py
│   └── ...
├── docs/                 # 指标文档与对齐说明
├── assets/
│   ├── finance-indicator-openapi.jar
│   └── libformula.so
└── http_client.py        # 数据获取器
```

## 按任务定位代码
| 任务 | 位置 | 说明 |
|------|----------|-------|
| 添加/修改指标 | `indicators/signals.py` | 核心信号逻辑 |
| 公式计算 | `indicators/libformula.py` | 通过 JNI 桥接 `libformula.so` |
| 技术分析封装 | `indicators/ta.py` | 封装层 |
| 获取行情数据 | `http_client.py` | 数据源 HTTP 客户端 |
| CLI 脚本 | `scripts/` | 工具脚本与检查程序 |

## 约定
- 通过 **JPype** 调用 `finance-indicator-openapi.jar`（JNI 桥接）。
- `libformula.so` 被原生加载用于公式求值。
- 指标参数定义在 `indicators/indicator_params.json` 中。

## 反模式
- 除非必要，不要在该技能外部直接导入指标内部模块 —— 公开 API 为 `indicators/__init__.py`。
