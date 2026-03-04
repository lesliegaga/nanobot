---
name: stock-analysis
description: 基于内部股票接口进行个股基础信息查询、日K数据获取，并计算多种技术指标与高级信号，用于技术面分析与解读。
metadata: '{"nanobot":{"emoji":"📈","requires":{"bins":["python"],"env":["STOCK_API_BASE"]}}}'
---

# 股票分析（Stock Analysis）

基于内部股票数据接口，为单只股票提供**基础信息查询、日K数据获取、常见技术指标计算（MA、MACD、RSI、布林带）以及若干高级技术信号识别与讲解**的能力。

> 默认假设你可以在当前工作空间根目录通过 `exec` 工具运行 `python` 命令。

## 何时使用本 Skill

在下列场景，应优先考虑使用本 skill：

- 用户提到：**“技术面分析 / 技术指标 / 技术形态 / 买卖信号”** 等需求；
- 用户希望基于**内部 UAT 股票接口**（而非公开 Tushare）分析某支股票；
- 用户提到具体技术指标：**MA5/10/20/60、MACD、RSI(6/12/14/24)、布林带**；
- 用户提到高级信号关键词：**“KD 出现一个向下/向上的风洞”、“牛背离”、“熊背离”、“MACD 反作用力”** 等；
- 用户希望针对**某一天或某一段时间**的 K 线进行技术面解读。

当你识别到这些需求时，请使用 `exec` 调用本 skill 的 CLI，而不是自己手写 HTTP 请求。

## 环境约定

- `STOCK_API_BASE`：可选环境变量，指定股票接口网关基址，默认为\
  `http://uat-nbai-gw.caizidao.com.cn/business/security/api`。
- `STOCK_SKILL_CACHE_DIR`：可选环境变量，指定本 skill 在本地落盘缓存 JSON 结果的根目录；\
  若不配置，则默认使用 skill 目录下的 `.cache` 子目录。
- 所有日期统一使用 `YYYY-MM-DD` 字符串格式（例如 `2025-06-25`）。
- 股票 `fullCode` 统一使用形如 `SH600000`、`SZ000001`、`OC874239` 的证券代码。

## 提供的能力与子命令

CLI 位于：

```bash
python nanobot/skills/stock-analysis/scripts/cli.py <subcommand> ...
```

### 1. 基础信息查询（basic）

用于获取单只股票或当日全市场的基础信息（类似 Tushare `stock_basic`）。

#### 用法

```bash
# 查询单只股票基础信息
python nanobot/skills/stock-analysis/scripts/cli.py basic \
  --full-code SH600036

# 查询当日全量基础信息（慎用，数据量较大）
python nanobot/skills/stock-analysis/scripts/cli.py basic

# 大数据量场景下，CLI 会自动将完整结果写入缓存文件，仅在 stdout 返回轻量摘要（包含 filePath 与 cacheRef），无需手动指定输出文件。
```

#### 返回示例（缩略）

```json
{
  "ok": true,
  "type": "basic",
  "fullCode": "SH600036",
  "items": [
    {
      "ts_code": "600036.SH",
      "symbol": "600036",
      "name": "招商银行",
      "area": "广东省",
      "industry": "股份制银行",
      "market": "主板",
      "list_date": "20020409"
    }
  ]
}
```

你可以直接根据 `items[0]` 中的字段，用中文给出公司概况（名称、行业、上市时间等）。

### 2. 日K数据查询（daily）

用于获取单只股票的**前复权日 K 线**数据（类似 Tushare `daily`），便于后续计算指标。

#### 用法

```bash
python nanobot/skills/stock-analysis/scripts/cli.py daily \
  --full-code SH600036 \
  --start-date 2025-06-01 \
  --count 60

# 当 count 很大时，同样会自动将完整结果写入缓存文件，stdout 只返回轻量摘要。
```

#### 返回示例（缩略）

```json
{
  "ok": true,
  "type": "daily",
  "fullCode": "SH600036",
  "bars": [
    {
      "trade_date": "2025-06-19",
      "open": 42.83,
      "high": 43.04,
      "low": 42.39,
      "close": 42.63,
      "pre_close": 42.83,
      "change": -0.2,
      "pct_chg": -0.0047,
      "vol": 513454,
      "amount": 2342843184
    }
  ]
}
```

日 K 结果会按交易日期从旧到新排序。你可以直接用这些字段回答“近期涨跌幅、成交量、波动区间”等问题。

### 3. 常规技术指标计算（indicators）

在给定日期附近，基于前复权日 K 数据计算多种常见技术指标：

- **移动平均线**：`MA5`、`MA10`、`MA20`、`MA60`；
- **MACD**：`DIF`、`DEA`、`MACD`（标准 12, 26, 9 参数）；
- **RSI**：`RSI6`、`RSI12`、`RSI14`、`RSI24`；
- **布林带**：`BOLL_UP`、`BOLL_MID`、`BOLL_LOW`（默认 20 日，2 倍标准差）。

#### 用法

```bash
python nanobot/skills/stock-analysis/scripts/cli.py indicators \
  --full-code SH600036 \
  --date 2025-06-25 \
  --lookback 120

# 当已通过 daily 子命令获取并落盘了日K数据时，可以复用文件，避免重复 HTTP 请求：
python nanobot/skills/stock-analysis/scripts/cli.py indicators \
  --full-code SH600036 \
  --date 2025-06-25 \
  --lookback 120 \
  --daily-file "D:/git/nanobot/.data/stock/SH600036_daily_2025-06-01_500.json"

# 指标计算结果也会自动写入缓存文件，stdout 仅返回带有 filePath 与 cacheRef 的摘要。
```

> `lookback` 为向前取日 K 的数量，用于计算长周期指标，一般建议不少于 60。

#### 返回示例（缩略）

```json
{
  "ok": true,
  "type": "indicators",
  "fullCode": "SH600036",
  "date": "2025-06-25",
  "price": {
    "open": 43.68,
    "high": 44.38,
    "low": 43.53,
    "close": 44.38,
    "vol": 607679,
    "amount": 2862914073
  },
  "indicators": {
    "MA5": 43.57,
    "MA10": 43.12,
    "MA20": 42.80,
    "MA60": 40.15,
    "MACD_DIF": 0.25,
    "MACD_DEA": 0.18,
    "MACD": 0.14,
    "RSI6": 68.3,
    "RSI12": 61.2,
    "RSI14": 59.7,
    "RSI24": 55.1,
    "BOLL_UP": 45.20,
    "BOLL_MID": 42.90,
    "BOLL_LOW": 40.60
  }
}
```

拿到结果后，你应该：

- 先用中文解释整体多空强弱（例如：MA 排列、MACD 是否多头、RSI 是否超买/超卖、股价在布林带中的位置等）；
- 再结合用户问题（如“还能不能追高”、“是否有回调压力”）做出有逻辑的技术面判断，并明确说明这是技术分析参考，不构成投资建议。

### 4. 高级技术信号识别（signals）

基于一段时间的日 K 与指标结果，识别若干**具有代表性的高级技术信号**，并给出简要中文说明。

当前实现的代表性信号包括（会逐步扩展）：

- **KD 向下的风洞**（`KD_DOWN_GAP`）；
- **KD 向上的风洞**（`KD_UP_GAP`）；
- **MACD 向上的反作用力**（`MACD_UP_REACTION`）；
- **MACD 向下的反作用力**（`MACD_DOWN_REACTION`）；
- **MACD 牛背离**（`MACD_BULL_DIV`）；
- **MACD 熊背离**（`MACD_BEAR_DIV`）。

#### 用法

```bash
python nanobot/skills/stock-analysis/scripts/cli.py signals \
  --full-code SH600036 \
  --date 2025-06-25 \
  --lookback 160

# 复用已有 daily 结果文件：
python nanobot/skills/stock-analysis/scripts/cli.py signals \
  --full-code SH600036 \
  --date 2025-06-25 \
  --lookback 160 \
  --daily-file "D:/git/nanobot/.data/stock/SH600036_daily_2025-06-01_500.json"

# 信号识别结果同样会自动写入缓存文件，stdout 仅返回带有 filePath 与 cacheRef 的摘要。
```

#### 返回示例（缩略）

```json
{
  "ok": true,
  "type": "signals",
  "fullCode": "SH600036",
  "date": "2025-06-25",
  "signals": [
    {
      "id": "KD_DOWN_GAP",
      "matched": true,
      "level": "warning",
      "title": "KD 出現一個向下的風洞",
      "summary": "9日K 值在前兩日曾向上交叉 9 日D，當日又向下交叉，技術上稱為「向下的風洞」，下跌風險加大。",
      "details": "……"
    }
  ]
}
```

拿到 `signals` 列表后，你应该：

- 逐条用中文解释这些信号的含义与可能的市场含义（例如下跌风险加大、可能诱空/诱多等）；
- 结合日 K 与指标结果，说明这些信号**并非绝对**，只是提高某种走势的概率；
- 明确提醒用户：所有信号仅供学习与参考，不构成任何投资建议或买卖指令。

## 错误处理约定

CLI 在遇到错误或数据不足时，会返回：

```json
{
  "ok": false,
  "error": {
    "code": "HTTP_ERROR",
    "message": "请求股票日K数据失败: ...."
  }
}
```

或：

```json
{
  "ok": false,
  "error": {
    "code": "NO_DATA",
    "message": "指定日期附近没有足够的日K数据计算指标"
  }
}
```

当 `ok` 为 `false` 时：

- 不要假装自己算出了指标或信号；
- 直接用中文解释失败原因（例如“接口无数据”或“lookback 过短”等），并根据错误信息尝试调整参数（比如：向前取更长的 `lookback`，或换一个交易日）再尝试一次；
- 如果多次失败，请坦诚告知用户当前无法完成精确技术分析，可以仅基于已有少量数据做一个**定性**的粗略判断，并说明局限性。

## 使用建议

- 在一次会话中，如果用户持续分析同一支股票，可以复用最近一次 `indicators` 或 `signals` 的结果，避免重复调用；\
  在大数据量场景（如长周期 `daily`、全市场 `basic`）下，本 CLI 会自动将完整 JSON 结果写入本地缓存文件（`STOCK_SKILL_CACHE_DIR` 或默认 `.cache` 目录），\
  stdout 仅返回带有 `filePath` / `cacheRef` 的轻量摘要，你应该通过文件系统工具按需读取关键字段，而不是在对话中传递整份 JSON；
- 当用户只问**定性问题**（例如“这只股票最近是不是很强势？”），可以适当缩短 `lookback`；\
  当用户问**趋势结构**（例如“过去几个月是否有明显头部/底部结构？”），应适当拉长 `lookback`；
- 避免向用户输出原始 JSON；\
  应该先在内部解析数值，再用通俗易懂的中文进行解释，并在必要时引用少量关键数字（如价格、涨跌幅、RSI 大致区间等）。

