from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

import sys
from pathlib import Path

# 添加 stock-analysis 目录到路径以支持导入
SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from http_client import DailyBar


Number = float


def simple_ma(values: Sequence[Number], window: int) -> List[Optional[Number]]:
    """
    简单移动平均线。
    返回与 values 等长的列表，前 window-1 项为 None。
    """
    n = len(values)
    if window <= 0:
        raise ValueError("window 必须为正整数")
    if n == 0:
        return []

    result: List[Optional[Number]] = [None] * n
    if n < window:
        return result

    window_sum = sum(values[:window])
    result[window - 1] = window_sum / window

    for i in range(window, n):
        window_sum += values[i] - values[i - window]
        result[i] = window_sum / window

    return result


def ema(values: Sequence[Number], span: int) -> List[Number]:
    """
    指数移动平均线。
    采用标准公式：EMA_t = alpha * price_t + (1 - alpha) * EMA_{t-1}
    """
    if span <= 0:
        raise ValueError("span 必须为正整数")
    n = len(values)
    if n == 0:
        return []

    alpha = 2.0 / (span + 1)
    result: List[Number] = []
    ema_prev = float(values[0])
    result.append(ema_prev)
    for i in range(1, n):
        price = float(values[i])
        ema_prev = alpha * price + (1.0 - alpha) * ema_prev
        result.append(ema_prev)
    return result


def compute_macd(
    closes: Sequence[Number],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[List[Number], List[Number], List[Number]]:
    """
    计算 MACD 指标：DIF、DEA、MACD。

    返回 (dif_list, dea_list, macd_hist_list)，长度与 closes 一致。
    MACD 柱线使用常见定义：2 * (DIF - DEA)。
    """
    n = len(closes)
    if n == 0:
        return [], [], []

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    # 对齐长度
    length = min(len(ema_fast), len(ema_slow))
    dif: List[Number] = [ema_fast[i] - ema_slow[i] for i in range(length)]

    # 如有长度差异，填补到和原始长度一致
    if length < n:
        last = dif[-1] if dif else 0.0
        dif.extend([last] * (n - length))

    dea = ema(dif, signal)
    # 对齐 DEA 长度
    if len(dea) < n:
        last_dea = dea[-1] if dea else 0.0
        dea.extend([last_dea] * (n - len(dea)))

    macd_hist: List[Number] = [2.0 * (dif[i] - dea[i]) for i in range(n)]
    return dif, dea, macd_hist


def _rsi(values: Sequence[Number], period: int) -> List[Optional[Number]]:
    """
    Wilder 风格 RSI 实现。
    返回与 values 等长的列表，前若干项为 None。
    """
    n = len(values)
    if period <= 0:
        raise ValueError("period 必须为正整数")
    if n == 0:
        return []

    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        delta = float(values[i]) - float(values[i - 1])
        if delta > 0:
            gains[i] = delta
        elif delta < 0:
            losses[i] = -delta

    result: List[Optional[Number]] = [None] * n
    if n <= period:
        return result

    # 初始平均值
    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period

    # 第一个有效 RSI
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - 100.0 / (1.0 + rs)

    # 递推
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - 100.0 / (1.0 + rs)

    return result


def compute_rsi(
    closes: Sequence[Number],
    periods: Sequence[int] = (6, 12, 14, 24),
) -> Dict[str, List[Optional[Number]]]:
    """
    计算多周期 RSI，返回字典，例如：
    {
        "RSI6": [...],
        "RSI12": [...],
        ...
    }
    """
    result: Dict[str, List[Optional[Number]]] = {}
    for p in periods:
        key = f"RSI{p}"
        result[key] = _rsi(closes, p)
    return result


def compute_bollinger(
    closes: Sequence[Number],
    period: int = 20,
    k: float = 2.0,
) -> Tuple[List[Optional[Number]], List[Optional[Number]], List[Optional[Number]]]:
    """
    计算布林带：上轨、中轨、下轨。
    """
    import math

    n = len(closes)
    if n == 0:
        return [], [], []
    if period <= 0:
        raise ValueError("period 必须为正整数")

    mid: List[Optional[Number]] = [None] * n
    up: List[Optional[Number]] = [None] * n
    low: List[Optional[Number]] = [None] * n

    if n < period:
        return up, mid, low

    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        var = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(var)

        mid[i] = mean
        up[i] = mean + k * std
        low[i] = mean - k * std

    return up, mid, low


def compute_all_indicators(
    bars: List[DailyBar],
    target_date: date,
) -> Dict[str, Any]:
    """
    计算目标日期的价格信息与各类技术指标。

    返回结构：
    {
        "price": {...},
        "indicators": {
            "MA5": ...,
            "MA10": ...,
            "MA20": ...,
            "MA60": ...,
            "MACD_DIF": ...,
            "MACD_DEA": ...,
            "MACD": ...,
            "RSI6": ...,
            "RSI12": ...,
            "RSI14": ...,
            "RSI24": ...,
            "BOLL_UP": ...,
            "BOLL_MID": ...,
            "BOLL_LOW": ...
        }
    }
    """
    if not bars:
        raise ValueError("bars 不能为空")

    # 按日期排序，确保时间序列正确
    ordered = sorted(bars, key=lambda b: b.trade_date)
    closes = [b.close for b in ordered]
    opens = [b.open for b in ordered]
    highs = [b.high for b in ordered]
    lows = [b.low for b in ordered]
    vols = [b.vol for b in ordered]
    amounts = [b.amount for b in ordered]

    index_map = {b.trade_date: idx for idx, b in enumerate(ordered)}
    if target_date not in index_map:
        raise ValueError(f"未找到目标交易日 {target_date.isoformat()} 的日K 数据")
    idx = index_map[target_date]

    ma5 = simple_ma(closes, 5)
    ma10 = simple_ma(closes, 10)
    ma20 = simple_ma(closes, 20)
    ma60 = simple_ma(closes, 60)

    dif, dea, macd_hist = compute_macd(closes)
    rsi_dict = compute_rsi(closes)
    boll_up, boll_mid, boll_low = compute_bollinger(closes)

    def _at(seq: Sequence[Optional[Number]], i: int) -> Optional[Number]:
        return seq[i] if 0 <= i < len(seq) else None

    price = {
        "open": float(opens[idx]),
        "high": float(highs[idx]),
        "low": float(lows[idx]),
        "close": float(closes[idx]),
        "vol": float(vols[idx]),
        "amount": float(amounts[idx]),
        "trade_date": ordered[idx].trade_date.isoformat(),
    }

    indicators: Dict[str, Any] = {
        "MA5": _at(ma5, idx),
        "MA10": _at(ma10, idx),
        "MA20": _at(ma20, idx),
        "MA60": _at(ma60, idx),
        "MACD_DIF": _at(dif, idx),
        "MACD_DEA": _at(dea, idx),
        "MACD": _at(macd_hist, idx),
        "RSI6": _at(rsi_dict.get("RSI6", []), idx),
        "RSI12": _at(rsi_dict.get("RSI12", []), idx),
        "RSI14": _at(rsi_dict.get("RSI14", []), idx),
        "RSI24": _at(rsi_dict.get("RSI24", []), idx),
        "BOLL_UP": _at(boll_up, idx),
        "BOLL_MID": _at(boll_mid, idx),
        "BOLL_LOW": _at(boll_low, idx),
    }

    return {"price": price, "indicators": indicators}


__all__ = [
    "simple_ma",
    "ema",
    "compute_macd",
    "compute_rsi",
    "compute_bollinger",
    "compute_all_indicators",
]

