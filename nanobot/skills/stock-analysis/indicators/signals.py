from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

import sys
from pathlib import Path

# 添加 stock-analysis 目录到路径以支持导入
SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from http_client import DailyBar
from indicators.ta import compute_macd, compute_bollinger, ema, simple_ma


Number = float


@dataclass
class Signal:
    id: str
    date: date
    level: str  # "info" | "warning" | "danger"
    title: str
    summary: str
    details: str

    def to_json(self) -> Dict[str, Any]:
        data = asdict(self)
        data["date"] = self.date.isoformat()
        return data


def _compute_kd(
    bars: Sequence[DailyBar],
    n: int = 9,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> Tuple[List[Number], List[Number]]:
    """
    计算 9 日 KD 指标（RSV + 平滑）。
    """
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    length = len(closes)
    if length == 0:
        return [], []

    rsv: List[Number] = [50.0] * length
    for i in range(length):
        start = max(0, i - n + 1)
        window_high = max(highs[start : i + 1])
        window_low = min(lows[start : i + 1])
        if window_high == window_low:
            rsv[i] = 50.0
        else:
            rsv[i] = (closes[i] - window_low) / (window_high - window_low) * 100.0

    k: List[Number] = [50.0] * length
    d: List[Number] = [50.0] * length
    alpha_k = 1.0 / k_smooth
    alpha_d = 1.0 / d_smooth
    for i in range(1, length):
        k[i] = alpha_k * rsv[i] + (1.0 - alpha_k) * k[i - 1]
        d[i] = alpha_d * k[i] + (1.0 - alpha_d) * d[i - 1]

    return k, d


def _cross_up(a_prev: Number, a_curr: Number, b_prev: Number, b_curr: Number) -> bool:
    return a_prev <= b_prev and a_curr > b_curr


def _cross_down(a_prev: Number, a_curr: Number, b_prev: Number, b_curr: Number) -> bool:
    return a_prev >= b_prev and a_curr < b_curr


def _find_index_by_date(bars: Sequence[DailyBar], target_date: date) -> Optional[int]:
    for idx, b in enumerate(bars):
        if b.trade_date == target_date:
            return idx
    return None


def detect_kd_down_gap(bars: Sequence[DailyBar], target_date: date) -> Optional[Signal]:
    """
    KD 出现一个向下的风洞：
    - 昨天或前天两天中，9 日 K 值曾向上交叉 9 日 D 值；
    - 当天 9 日 K 值向下交叉 9 日 D 值。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 2:
        return None

    k, d = _compute_kd(bars)
    if len(k) <= idx:
        return None

    # 当天向下交叉
    if not _cross_down(k[idx - 1], k[idx], d[idx - 1], d[idx]):
        return None

    # 昨天或前天曾经向上交叉
    up_cross = False
    for j in (idx - 1, idx - 2):
        if j <= 0:
            continue
        if _cross_up(k[j - 1], k[j], d[j - 1], d[j]):
            up_cross = True
            break
    if not up_cross:
        return None

    return Signal(
        id="KD_DOWN_GAP",
        date=target_date,
        level="warning",
        title="KD 出現一個向下的風洞",
        summary="9 日 K 值在前两日向上交叉 D 值，当日又向下交叉，形成「向下的风洞」，下跌风险加大。",
        details=(
            "根据文档定义：昨天或前天两天中，9 日 K 值曾经向上交叉 9 日 D 值，"
            "而当天 9 日 K 值又向下交叉 9 日 D 值，这通常意味着上一段反弹结束，"
            "容易引发新一波下跌行情，尤其在经历一段下跌后的反弹阶段更需谨慎。"
        ),
    )


def detect_kd_up_gap(bars: Sequence[DailyBar], target_date: date) -> Optional[Signal]:
    """
    KD 出现一个向上的风洞：
    - 昨天或前天两天中，9 日 K 值曾向下交叉 9 日 D 值；
    - 当天 9 日 K 值向上交叉 9 日 D 值。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 2:
        return None

    k, d = _compute_kd(bars)
    if len(k) <= idx:
        return None

    # 当天向上交叉
    if not _cross_up(k[idx - 1], k[idx], d[idx - 1], d[idx]):
        return None

    # 昨天或前天曾经向下交叉
    down_cross = False
    for j in (idx - 1, idx - 2):
        if j <= 0:
            continue
        if _cross_down(k[j - 1], k[j], d[j - 1], d[j]):
            down_cross = True
            break
    if not down_cross:
        return None

    return Signal(
        id="KD_UP_GAP",
        date=target_date,
        level="info",
        title="KD 出現一個向上的風洞",
        summary="9 日 K 值在前两日向下交叉 D 值，当日又向上交叉，形成「向上的风洞」，反弹概率提高。",
        details=(
            "根据文档定义：昨天或前天两天中，9 日 K 值曾经向下交叉 9 日 D 值，"
            "而当天 9 日 K 值又向上交叉 9 日 D 值，这通常是一种多头的骗线与洗牌，"
            "行情在甩掉跟风者之后，后续继续向上发展的概率会提高。"
        ),
    )


def _compute_macd_series(bars: Sequence[DailyBar]) -> Tuple[List[Number], List[Number], List[Number]]:
    closes = [b.close for b in bars]
    return compute_macd(closes)


# TODO: 该 CCI 实现为合理近似版本，待有原始公式后校正。
def _cci_series(bars: Sequence[DailyBar], period: int = 20) -> List[Optional[Number]]:
    """
    简化版 CCI：使用典型价 (H+L+C)/3 与其移动平均和平均偏差。
    """
    n = len(bars)
    if n == 0:
        return []
    if period <= 0:
        raise ValueError("period 必须为正整数")

    tp: List[Number] = [(b.high + b.low + b.close) / 3.0 for b in bars]
    ma_tp = simple_ma(tp, period)

    result: List[Optional[Number]] = [None] * n
    for i in range(period - 1, n):
        if ma_tp[i] is None:
            continue
        start = i - period + 1
        window = tp[start : i + 1]
        mean = ma_tp[i]
        md = sum(abs(x - mean) for x in window) / period
        if md == 0:
            result[i] = 0.0
        else:
            result[i] = (tp[i] - mean) / (0.015 * md)
    return result


# TODO: 该 PVI 实现为合理近似版本，待有原始公式后校正。
def _pvi_series(bars: Sequence[DailyBar]) -> List[Number]:
    """
    正量指标 PVI：仅在收盘价上涨时累加量能变化。
    """
    n = len(bars)
    if n == 0:
        return []
    pvi: List[Number] = [1000.0]
    for i in range(1, n):
        prev = bars[i - 1]
        cur = bars[i]
        if cur.close > prev.close and prev.vol > 0:
            change = (cur.vol - prev.vol) / prev.vol
            pvi.append(pvi[-1] * (1.0 + change))
        else:
            pvi.append(pvi[-1])
    return pvi


# TODO: 该 OBV 实现为合理近似版本，待有原始公式后校正。
def _obv_series(bars: Sequence[DailyBar]) -> List[Number]:
    """
    OBV 能量潮：按涨跌方向累加成交量。
    """
    n = len(bars)
    if n == 0:
        return []
    obv: List[Number] = [0.0]
    for i in range(1, n):
        prev = bars[i - 1]
        cur = bars[i]
        if cur.close > prev.close:
            obv.append(obv[-1] + cur.vol)
        elif cur.close < prev.close:
            obv.append(obv[-1] - cur.vol)
        else:
            obv.append(obv[-1])
    return obv


# TODO: 该 DPO 实现为合理近似版本，待有原始公式后校正。
def _dpo_series(closes: Sequence[Number], period: int = 20) -> List[Optional[Number]]:
    """
    简化版 DPO：当前收盘价减去相同周期的简单移动平均。
    """
    n = len(closes)
    if n == 0:
        return []
    ma = simple_ma(closes, period)
    result: List[Optional[Number]] = [None] * n
    for i in range(n):
        if ma[i] is None:
            continue
        result[i] = closes[i] - ma[i]  # type: ignore[operator]
    return result


# TODO: 该 MOM 实现为合理近似版本，待有原始公式后校正。
def _mom_series(closes: Sequence[Number], period: int = 10) -> List[Optional[Number]]:
    """
    MOM：收盘价与若干天前价格之差。
    """
    n = len(closes)
    if n == 0:
        return []
    result: List[Optional[Number]] = [None] * n
    for i in range(period, n):
        result[i] = closes[i] - closes[i - period]
    return result


# TODO: 该 EMV 实现为合理近似版本，待有原始公式后校正。
def _emv_series(bars: Sequence[DailyBar]) -> List[Optional[Number]]:
    """
    EMV：简化版 Ease of Movement。
    """
    n = len(bars)
    if n == 0:
        return []
    result: List[Optional[Number]] = [None] * n
    for i in range(1, n):
        prev = bars[i - 1]
        cur = bars[i]
        mid_prev = (prev.high + prev.low) / 2.0
        mid_curr = (cur.high + cur.low) / 2.0
        distance = mid_curr - mid_prev
        spread = cur.high - cur.low
        if spread == 0 or cur.vol == 0:
            result[i] = 0.0
        else:
            result[i] = (distance / spread) * (spread / cur.vol)
    return result


# TODO: 该终极指标实现为常见 Ultimate Oscillator 公式的近似版本，待有原始参数后校正。
def _ultimate_oscillator(bars: Sequence[DailyBar]) -> List[Number]:
    """
    终极指标（Ultimate Oscillator）的近似实现。
    """
    n = len(bars)
    if n == 0:
        return []
    bp: List[Number] = [0.0] * n
    tr: List[Number] = [0.0] * n
    for i in range(1, n):
        prev_close = bars[i - 1].close
        cur = bars[i]
        low = min(cur.low, prev_close)
        high = max(cur.high, prev_close)
        bp[i] = cur.close - low
        tr[i] = high - low if high != low else 1e-9

    def avg(idx: int, period: int) -> Number:
        start = max(1, idx - period + 1)
        bp_sum = sum(bp[start : idx + 1])
        tr_sum = sum(tr[start : idx + 1])
        if tr_sum <= 0:
            return 0.0
        return bp_sum / tr_sum

    result: List[Number] = [0.0] * n
    for i in range(1, n):
        a7 = avg(i, 7)
        a14 = avg(i, 14)
        a28 = avg(i, 28)
        result[i] = 100.0 * (4 * a7 + 2 * a14 + a28) / 7.0
    return result


# TODO: 该 VR 实现为常见教科书公式的近似版本，待有原始参数后校正。
def _vr_series(bars: Sequence[DailyBar], period: int = 26) -> List[Optional[Number]]:
    """
    VR 量能比率：简化版，采用上涨量/下跌量统计。
    """
    n = len(bars)
    if n == 0:
        return []
    av: List[Number] = [0.0] * n
    bv: List[Number] = [0.0] * n
    cv: List[Number] = [0.0] * n
    for i in range(1, n):
        prev = bars[i - 1]
        cur = bars[i]
        if cur.close > prev.close:
            av[i] = cur.vol
        elif cur.close < prev.close:
            bv[i] = cur.vol
        else:
            cv[i] = cur.vol

    result: List[Optional[Number]] = [None] * n
    for i in range(period, n):
        start = i - period + 1
        av_sum = sum(av[start : i + 1])
        bv_sum = sum(bv[start : i + 1])
        cv_sum = sum(cv[start : i + 1])
        denom = bv_sum + 0.5 * cv_sum
        if denom == 0:
            result[i] = None
        else:
            result[i] = (av_sum + 0.5 * cv_sum) / denom * 100.0
    return result


# TODO: 该 CR 实现为常见教科书公式的近似版本，待有原始参数后校正。
def _cr_series(bars: Sequence[DailyBar], period: int = 26) -> List[Optional[Number]]:
    """
    CR 指标：基于前一日中价的简化实现。
    """
    n = len(bars)
    if n == 0:
        return []
    pm: List[Number] = [0.0] * n
    for i in range(1, n):
        prev = bars[i - 1]
        pm[i] = (prev.high + prev.low + prev.close) / 3.0

    up: List[Number] = [0.0] * n
    down: List[Number] = [0.0] * n
    for i in range(1, n):
        cur = bars[i]
        if cur.high > pm[i]:
            up[i] = cur.high - max(pm[i], cur.low)
        if cur.low < pm[i]:
            down[i] = min(pm[i], cur.high) - cur.low

    result: List[Optional[Number]] = [None] * n
    for i in range(period, n):
        start = i - period + 1
        up_sum = sum(up[start : i + 1])
        down_sum = sum(down[start : i + 1])
        if down_sum == 0:
            result[i] = None
        else:
            result[i] = up_sum / down_sum * 100.0
    return result


# TODO: 该 BR/AR 实现为常见教科书公式的近似版本，待有原始参数后校正。
def _br_ar_series(bars: Sequence[DailyBar], period: int = 26) -> Tuple[List[Optional[Number]], List[Optional[Number]]]:
    """
    BR / AR 指标的简化实现。
    """
    n = len(bars)
    if n == 0:
        return [], []
    br_up: List[Number] = [0.0] * n
    br_down: List[Number] = [0.0] * n
    ar_up: List[Number] = [0.0] * n
    ar_down: List[Number] = [0.0] * n

    for i in range(1, n):
        prev = bars[i - 1]
        cur = bars[i]
        # BR
        if cur.high > prev.close:
            br_up[i] = cur.high - prev.close
        if cur.low < prev.close:
            br_down[i] = prev.close - cur.low
        # AR
        if cur.high > cur.open:
            ar_up[i] = cur.high - cur.open
        if cur.low < cur.open:
            ar_down[i] = cur.open - cur.low

    br: List[Optional[Number]] = [None] * n
    ar: List[Optional[Number]] = [None] * n
    for i in range(period, n):
        start = i - period + 1
        bu = sum(br_up[start : i + 1])
        bd = sum(br_down[start : i + 1])
        au = sum(ar_up[start : i + 1])
        ad = sum(ar_down[start : i + 1])
        br[i] = None if bd == 0 else bu / bd * 100.0
        ar[i] = None if ad == 0 else au / ad * 100.0
    return br, ar


# TODO: 该中期方向线实现为合理近似版本，待有原始公式后校正。
def _mid_direction_series(bars: Sequence[DailyBar]) -> List[Number]:
    """
    中期方向线：使用 20 日与 60 日 EMA 差值的百分比表示中期趋势强弱。
    """
    closes = [b.close for b in bars]
    if not closes:
        return []
    ema20 = ema(closes, 20)
    ema60 = ema(closes, 60)
    length = min(len(ema20), len(ema60))
    result: List[Number] = []
    for i in range(length):
        denom = ema60[i] if ema60[i] != 0 else 1e-9
        result.append((ema20[i] - ema60[i]) / denom * 100.0)
    # 如有长度差异，用最后一个值填充
    if length < len(closes):
        last = result[-1] if result else 0.0
        result.extend([last] * (len(closes) - length))
    return result


# TODO: 该價差引力实现为合理近似版本，待有原始公式后校正。
def _price_gravity_series(bars: Sequence[DailyBar], period: int = 20) -> List[Number]:
    """
    價差引力：使用价格相对中期均线的偏离程度近似。
    """
    closes = [b.close for b in bars]
    if not closes:
        return []
    ema_mid = ema(closes, period)
    result: List[Number] = []
    for c, m in zip(closes, ema_mid):
        denom = m if m != 0 else 1e-9
        result.append((c - m) / denom * 100.0)
    return result


# TODO: 邱氏天地線目前用布林帶位置近似，待有原始公式後校正。
def _qiu_tiandi_series(bars: Sequence[DailyBar]) -> List[Number]:
    """
    邱氏天地線：用布林帶位置近似，>30 視為短期波峰區，<0 視為波谷區。
    """
    closes = [b.close for b in bars]
    if not closes:
        return []
    up, mid, low = compute_bollinger(closes, period=20, k=2.0)
    n = len(closes)
    result: List[Number] = [0.0] * n
    for i in range(n):
        if mid[i] is None or up[i] is None:
            result[i] = 0.0
            continue
        denom = up[i] - mid[i]
        if denom == 0:
            result[i] = 0.0
        else:
            val = (closes[i] - mid[i]) / denom * 100.0
            # 限制在 [-100, 100] 範圍內
            if val > 100.0:
                val = 100.0
            elif val < -100.0:
                val = -100.0
            result[i] = val
    return result


# TODO: 扳機線目前用價格相對 EMA 的波動強度近似，待有原始公式後校正。
def _trigger_line_series(closes: Sequence[Number], period: int) -> List[Number]:
    """
    扳機線：使用價格相對自身 EMA 的波動幅度近似，數值越高代表趨勢越強。
    """
    if not closes:
        return []
    ema_p = ema(closes, period)
    result: List[Number] = []
    for c, m in zip(closes, ema_p):
        denom = m if m != 0 else 1e-9
        result.append(abs(c - m) / denom * 100.0)
    return result


# TODO: 變動式超買/超賣線目前以布林帶近似，待有原始算法後校正。
def _dynamic_band(series: Sequence[Number], period: int = 20, k: float = 2.0) -> Tuple[List[Optional[Number]], List[Optional[Number]]]:
    """
    對任意數列套用布林帶作為變動式超買/超賣線，返回 (lower, upper)。
    """
    up, mid, low = compute_bollinger(series, period=period, k=k)
    # compute_bollinger 返回 (up, mid, low)，這裡按「下軌=超賣線，上軌=超買線」使用
    lower = low
    upper = up
    return lower, upper


def detect_macd_up_reaction(bars: Sequence[DailyBar], target_date: date) -> Optional[Signal]:
    """
    MACD 向上的反作用力：
    - 昨天或前天两天中，DIF 曾向下交叉 DEA；
    - 当天 DIF 向上交叉 DEA。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 2:
        return None

    dif, dea, _ = _compute_macd_series(bars)
    if len(dif) <= idx or len(dea) <= idx:
        return None

    if not _cross_up(dif[idx - 1], dif[idx], dea[idx - 1], dea[idx]):
        return None

    down_cross = False
    for j in (idx - 1, idx - 2):
        if j <= 0:
            continue
        if _cross_down(dif[j - 1], dif[j], dea[j - 1], dea[j]):
            down_cross = True
            break
    if not down_cross:
        return None

    return Signal(
        id="MACD_UP_REACTION",
        date=target_date,
        level="info",
        title="MACD 疑似出現一個向上的反作用力",
        summary="DIF 在前两日曾向下交叉 DEA，当日又向上交叉，形成類似「拉弓射箭」的向上反作用力形態。",
        details=(
            "文档中将此形态比喻為「想要跳得高，必先蹲下來」，"
            "MACD 先向下交叉製造空頭假象，隨後迅速向上交叉，"
            "在指標上形成心眼形態，往往代表行情向上反轉的誘空陷阱。"
        ),
    )


def detect_macd_down_reaction(bars: Sequence[DailyBar], target_date: date) -> Optional[Signal]:
    """
    MACD 向下的反作用力：
    - 昨天或前天两天中，DIF 曾向上交叉 DEA；
    - 当天 DIF 向下交叉 DEA。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 2:
        return None

    dif, dea, _ = _compute_macd_series(bars)
    if len(dif) <= idx or len(dea) <= idx:
        return None

    if not _cross_down(dif[idx - 1], dif[idx], dea[idx - 1], dea[idx]):
        return None

    up_cross = False
    for j in (idx - 1, idx - 2):
        if j <= 0:
            continue
        if _cross_up(dif[j - 1], dif[j], dea[j - 1], dea[j]):
            up_cross = True
            break
    if not up_cross:
        return None

    return Signal(
        id="MACD_DOWN_REACTION",
        date=target_date,
        level="warning",
        title="MACD 疑似出現一個向下的反作用力",
        summary="DIF 在前两日曾向上交叉 DEA，当日又向下交叉，形成向下的反作用力形態，常見於誘多騙線。",
        details=(
            "文档中將此形態比喻為「股價起跑前的那一剎那會先擺盪」，"
            "MACD 先向上交叉吸引追多資金，隨後迅速向下交叉，"
            "在指標圖上留下心眼形態，常見於誘多後快速殺跌的走勢。"
        ),
    )


def _find_local_extrema(values: Sequence[Number], lookback: int, target_idx: int, kind: str) -> Optional[Tuple[int, int]]:
    """
    在 [target_idx - lookback, target_idx] 區間內尋找最近的兩個局部高點或低點索引。
    kind: "high" | "low"
    """
    start = max(1, target_idx - lookback)
    end = target_idx
    idxs: List[int] = []
    for i in range(start, end):
        if i <= 0 or i >= len(values) - 1:
            continue
        if kind == "high":
            if values[i] >= values[i - 1] and values[i] > values[i + 1]:
                idxs.append(i)
        else:
            if values[i] <= values[i - 1] and values[i] < values[i + 1]:
                idxs.append(i)
    if len(idxs) < 2:
        return None
    return idxs[-2], idxs[-1]


def detect_macd_bull_divergence(
    bars: Sequence[DailyBar],
    target_date: date,
    lookback: int = 22,
) -> Optional[Signal]:
    """
    近似實現 MACD 牛背離：
    - 22 日內找到兩個價格高點，後一個高點價格更高；
    - 對應 DIF 高點卻更低，即「股價一山比一山高，MACD 一山比一山低」。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 3:
        return None

    closes = [b.close for b in bars]
    dif, _, _ = _compute_macd_series(bars)
    if len(dif) <= idx:
        return None

    # 僅在 DIF 已經向下交叉或明顯回落附近關注此信號
    extrema = _find_local_extrema(closes, lookback=lookback, target_idx=idx, kind="high")
    if not extrema:
        return None
    i1, i2 = extrema
    if not (i2 == idx or i2 == idx - 1):
        return None

    price1, price2 = closes[i1], closes[i2]
    dif1, dif2 = dif[i1], dif[i2]
    if not (price2 > price1 and dif2 < dif1 and dif1 > 0 and dif2 > 0):
        return None

    return Signal(
        id="MACD_BULL_DIV",
        date=bars[i2].trade_date,
        level="warning",
        title="MACD 疑似出現牛背離",
        summary="股價一山比一山高，而 MACD 指標一山比一山低，屬於牛背離，行情可能由升轉跌。",
        details=(
            "文档中將牛背離描述為：股價高點一次比一次高，而 MACD 指標高點卻一次比一次低，"
            "顯示指標對多頭上漲產生懷疑，屬於「外強中乾」的訊號，"
            "常見於上漲末端，後續出現回調甚至反轉下跌的機率提高。"
        ),
    )


def detect_macd_bear_divergence(
    bars: Sequence[DailyBar],
    target_date: date,
    lookback: int = 22,
) -> Optional[Signal]:
    """
    近似實現 MACD 熊背離：
    - 22 日內找到兩個價格低點，後一個低點價格更低；
    - 對應 DIF 低點卻更高，即「股價一底比一底低，MACD 一底比一底高」。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 3:
        return None

    closes = [b.close for b in bars]
    dif, _, _ = _compute_macd_series(bars)
    if len(dif) <= idx:
        return None

    extrema = _find_local_extrema(closes, lookback=lookback, target_idx=idx, kind="low")
    if not extrema:
        return None
    i1, i2 = extrema
    if not (i2 == idx or i2 == idx - 1):
        return None

    price1, price2 = closes[i1], closes[i2]
    dif1, dif2 = dif[i1], dif[i2]
    if not (price2 < price1 and dif2 > dif1 and dif1 < 0 and dif2 < 0):
        return None

    return Signal(
        id="MACD_BEAR_DIV",
        date=bars[i2].trade_date,
        level="info",
        title="MACD 疑似出現熊背離",
        summary="股價一底比一底低，而 MACD 指標一底比一底高，屬於熊背離，行情可能由跌轉升。",
        details=(
            "文档中將熊背離描述為：股價低點一次比一次低，而 MACD 指標低點卻一次比一次高，"
            "顯示指標認為下跌動能逐漸衰竭，屬於空頭末端可能反轉的訊號，"
            "後續出現止跌回升的機率提高，但仍需搭配量能與其他指標綜合判斷。"
        ),
    )


def detect_macd_zero_cross_down(bars: Sequence[DailyBar], target_date: date) -> Optional[Signal]:
    """
    (9) MACD 向下跌破 0 軸變成負值。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return None

    dif, _, _ = _compute_macd_series(bars)
    if len(dif) <= idx:
        return None

    if not (dif[idx - 1] >= 0.0 and dif[idx] < 0.0):
        return None

    start = max(0, idx - 15)
    for j in range(start, idx):
        if dif[j] <= 0.0:
            return None

    return Signal(
        id="MACD_BELOW_ZERO",
        date=target_date,
        level="warning",
        title="MACD 向下跌破0軸變成負值",
        summary="DIF 由正轉負且前 15 日一直在 0 軸之上，短期步入空頭區域。",
        details=(
            "當 DIF 由高於 0 軸跌破至 0 軸之下，且前 15 天始終維持在 0 軸之上，"
            "代表多頭動能由盛轉衰，傳統技術分析會將此視為行情步入空頭區的警訊。"
        ),
    )


def detect_macd_zero_cross_up(bars: Sequence[DailyBar], target_date: date) -> Optional[Signal]:
    """
    (10) MACD 站上 0 軸變成正值。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return None

    dif, _, _ = _compute_macd_series(bars)
    if len(dif) <= idx:
        return None

    if not (dif[idx - 1] <= 0.0 and dif[idx] > 0.0):
        return None

    start = max(0, idx - 15)
    for j in range(start, idx):
        if dif[j] >= 0.0:
            return None

    return Signal(
        id="MACD_ABOVE_ZERO",
        date=target_date,
        level="info",
        title="MACD 站上0軸變成正值",
        summary="DIF 由負轉正且前 15 日一直在 0 軸之下，行情有轉入多頭的跡象。",
        details=(
            "當 DIF 由低於 0 軸重新站上 0 軸，且前 15 天始終維持在 0 軸之下，"
            "通常被視為行情由空頭走向多頭的重要信號，但也可能存在誘多騙線，"
            "需配合理想的量價結構與其他指標綜合判斷。"
        ),
    )


def detect_cci_upper_turn(bars: Sequence[DailyBar], target_date: date) -> Optional[Signal]:
    """
    (11) CCI 指標擺盪到了行情通道上軌：
    前一天 CCI >= 148，當天 CCI < 前一天。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return None

    cci = _cci_series(bars, period=20)
    if len(cci) <= idx or cci[idx - 1] is None or cci[idx] is None:
        return None

    prev = cci[idx - 1]  # type: ignore[assignment]
    curr = cci[idx]  # type: ignore[assignment]
    if prev >= 148.0 and curr < prev:
        return Signal(
            id="CCI_UPPER_TURN",
            date=target_date,
            level="warning",
            title="CCI指標擺盪到了行情通道上軌",
            summary="CCI 昨日位於 148 以上，今日出現向下轉折，短期小高點機率偏大。",
            details=(
                "根據文档說明，CCI 在 148 以上向下轉折時，代表價格已經來到行情通道的上軌，"
                "在此附近形成短期小高點的機率較高，但並不一定構成中長期反轉。"
            ),
        )
    return None


def detect_cci_lower_turn(bars: Sequence[DailyBar], target_date: date) -> Optional[Signal]:
    """
    (12) CCI 指標擺盪到了行情通道下軌：
    前一天 CCI <= -148，當天 CCI > 前一天。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return None

    cci = _cci_series(bars, period=20)
    if len(cci) <= idx or cci[idx - 1] is None or cci[idx] is None:
        return None

    prev = cci[idx - 1]  # type: ignore[assignment]
    curr = cci[idx]  # type: ignore[assignment]
    if prev <= -148.0 and curr > prev:
        return Signal(
            id="CCI_LOWER_TURN",
            date=target_date,
            level="info",
            title="CCI指標擺盪到了行情通道下軌",
            summary="CCI 昨日位於 -148 以下，今日出現向上轉折，短期小低點機率偏大。",
            details=(
                "根據文档說明，當 CCI 在 -148 以下出現向上轉折時，"
                "行情在此形成短期低點的機率較高，但仍需搭配量能與其他指標確認。"
            ),
        )
    return None


def detect_qiu_tiandi_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (13)-(18) 邱氏天地線相關信號的簡化實現。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None:
        return []
    q = _qiu_tiandi_series(bars)
    n = len(q)
    results: List[Signal] = []

    def _val(i: int) -> Optional[Number]:
        if 0 <= i < n:
            return q[i]
        return None

    curr = _val(idx)
    prev = _val(idx - 1)
    prev2 = _val(idx - 2)

    # (13) 當天由 <30 變成 >=30
    if prev is not None and curr is not None and prev < 30.0 and curr >= 30.0:
        results.append(
            Signal(
                id="QIU_ENTER_PEAK",
                date=target_date,
                level="info",
                title="邱氏天地線剛剛進入短期循環的小波峰區",
                summary="邱氏天地線由 30 以下上穿至 30 以上，價格循環進入短期波峰區，小高點機率增大。",
                details=(
                    "文档形容邱氏天地線像波浪一樣循環波動，"
                    "當數值超過 30 時，代表價格波動循環到了短期波峰區，"
                    "未來幾天在此價位附近形成小高點的機率較高。"
                ),
            )
        )

    # (14) 前天由 <30 變 >=30，昨天及今天皆 >=30
    if (
        prev2 is not None
        and prev is not None
        and curr is not None
        and prev2 < 30.0
        and prev >= 30.0
        and curr >= 30.0
    ):
        results.append(
            Signal(
                id="QIU_PEAK_2DAYS",
                date=target_date,
                level="warning",
                title="邱氏天地線進入小循環波峰已經二、三天了",
                summary="邱氏天地線在 30 以上維持多日，需觀察買盤與量能是否開始退潮。",
                details=(
                    "當邱氏天地線在 30 以上連續維持兩、三天，"
                    "代表短期波峰已經持續一段時間，需要特別關注量能是否續強，"
                    "一旦量能後繼無力，小高點或回調風險將升高。"
                ),
            )
        )

    # (15) 7 天前由 <30 變 >=30，連續 8 天皆 >=30
    if idx >= 7:
        v7_prev = _val(idx - 7)
        v7_prev_prev = _val(idx - 8)
        if (
            v7_prev_prev is not None
            and v7_prev is not None
            and v7_prev_prev < 30.0
            and v7_prev >= 30.0
        ):
            ok = True
            for j in range(idx - 7, idx + 1):
                v = _val(j)
                if v is None or v < 30.0:
                    ok = False
                    break
            if ok:
                results.append(
                    Signal(
                        id="QIU_PEAK_LONG",
                        date=target_date,
                        level="warning",
                        title="邱氏天地線維持在循環波峰已經好多天了",
                        summary="邱氏天地線在 30 以上維持至少 8 天，需留意行情是否形成較重要高點。",
                        details=(
                            "文档指出，當邱氏天地線在 30 以上長時間連續出現紅色標記，"
                            "代表行情偏強，但同時也要警惕可能已接近較高風險區域，"
                            "宜配合理想的量能與其他趨勢指標謹慎應對。"
                        ),
                    )
                )

    # (16) 當天由 >0 變 <=0
    if prev is not None and curr is not None and prev > 0.0 and curr <= 0.0:
        results.append(
            Signal(
                id="QIU_ENTER_VALLEY",
                date=target_date,
                level="info",
                title="邱氏天地線開始進入短期循環的小波谷區",
                summary="邱氏天地線由 0 軸以上跌至 0 軸以下，價格循環進入短期波谷區，小低點機率增大。",
                details=(
                    "文档中提到，邱氏天地線 <0 代表價格循環到了短期波谷區，"
                    "在這附近形成小低點的機率提高，但仍需搭配終極指標與 MFI 等量能指標綜合判斷。"
                ),
            )
        )

    # (17) 前天由 >0 變 <=0，昨天及今天皆 <=0
    if (
        prev2 is not None
        and prev is not None
        and curr is not None
        and prev2 > 0.0
        and prev <= 0.0
        and curr <= 0.0
    ):
        results.append(
            Signal(
                id="QIU_VALLEY_2DAYS",
                date=target_date,
                level="info",
                title="行情循環至邱氏天地線的短期低谷區已經二、三天了",
                summary="邱氏天地線在 0 軸以下維持多日，需觀察賣盤是否開始收斂。",
                details=(
                    "當邱氏天地線在 0 軸以下連續維持兩、三天，"
                    "代表行情在短期低谷徘徊，應特別觀察量能是否出現回升，"
                    "以及股價是否出現止跌企穩跡象。"
                ),
            )
        )

    # (18) 7 天前由 >0 變 <=0，連續 8 天皆 <=0
    if idx >= 7:
        v7_prev = _val(idx - 7)
        v7_prev_prev = _val(idx - 8)
        if (
            v7_prev_prev is not None
            and v7_prev is not None
            and v7_prev_prev > 0.0
            and v7_prev <= 0.0
        ):
            ok = True
            for j in range(idx - 7, idx + 1):
                v = _val(j)
                if v is None or v > 0.0:
                    ok = False
                    break
            if ok:
                results.append(
                    Signal(
                        id="QIU_VALLEY_LONG",
                        date=target_date,
                        level="warning",
                        title="邱氏天地線維持在弱勢循環蠻多天了",
                        summary="邱氏天地線在 0 軸以下維持至少 8 天，需關注量能是否有起死回生跡象。",
                        details=(
                            "文档提到，當邱氏天地線長時間停留在 0 軸以下，"
                            "代表行情處於相對弱勢狀態，若量能無法有效回升，"
                            "則短期內仍應保持謹慎；反之，量能復甦則可能帶來止跌回升機會。"
                        ),
                    )
                )

    return results


def detect_ultimate_osc_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (19)-(21) 終極指標相關信號。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return []
    uo = _ultimate_oscillator(bars)
    n = len(uo)
    if n <= idx:
        return []

    results: List[Signal] = []
    prev = uo[idx - 1]
    curr = uo[idx]

    # (19) 當天由 >35 變 <=35
    if prev > 35.0 and curr <= 35.0:
        results.append(
            Signal(
                id="UO_DROP_BELOW_35",
                date=target_date,
                level="info",
                title="終極指標掉入35以下的落袋區了",
                summary="終極指標由 35 以上跌入 35 以下，行情可能接近循環谷底。",
                details=(
                    "文档將終極指標跌入 35 以下比喻為台球掉入袋子裡，"
                    "暗示行情可能已經進入價格循環的相對低位區。"
                ),
            )
        )

    # (20) 7 天前由 >35 變 <=35，連續 8 天皆 <=35
    if idx >= 7:
        def _uo(i: int) -> Optional[Number]:
            return uo[i] if 0 <= i < n else None

        u7_prev = _uo(idx - 7)
        u7_prev_prev = _uo(idx - 8)
        if (
            u7_prev_prev is not None
            and u7_prev is not None
            and u7_prev_prev > 35.0
            and u7_prev <= 35.0
        ):
            ok = True
            for j in range(idx - 7, idx + 1):
                if _uo(j) is None or _uo(j) > 35.0:  # type: ignore[operator]
                    ok = False
                    break
            if ok:
                results.append(
                    Signal(
                        id="UO_LONG_BELOW_35",
                        date=target_date,
                        level="warning",
                        title="終極指標落袋已經好多天了",
                        summary="終極指標在 35 以下維持至少 8 天，等待重新站上 35。",
                        details=(
                            "文档指出，終極指標長時間維持在 35 以下，"
                            "代表行情持續偏弱，需要等待指標重新站回 35 之上，"
                            "並配合理想的量潮變化確認是否真正止跌回升。"
                        ),
                    )
                )

    # (21) 前一天 >=69，當天回落，且過去 7 天內未出現相同信號
    if prev >= 69.0 and curr < prev:
        # 檢查過去 7 天是否已出現過同樣條件
        seen = False
        for j in range(max(1, idx - 7), idx):
            if uo[j - 1] >= 69.0 and uo[j] < uo[j - 1]:
                seen = True
                break
        if not seen:
            results.append(
                Signal(
                    id="UO_EXTREME_UP",
                    date=target_date,
                    level="warning",
                    title="終極指標出現漲勢極端的信號",
                    summary="終極指標在高檔首次出現由升轉跌，暗示漲勢可能進入極端階段。",
                    details=(
                        "文档提到，當終極指標被拉到 69 以上並出現轉折時，"
                        "代表行情極為強勢但也可能接近強弩之末，"
                        "宜配合扳機線與其他趨勢指標來確認是否進入風險區。"
                    ),
                )
            )

    return results


def detect_trigger_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (22)-(24) 扳機線相關信號（7天與14天扳機線，高位轉折與半空中轉折）。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 2:
        return []

    closes = [b.close for b in bars]
    trig7 = _trigger_line_series(closes, 7)
    trig14 = _trigger_line_series(closes, 14)
    n7 = len(trig7)
    n14 = len(trig14)
    results: List[Signal] = []

    def _val7(i: int) -> Optional[Number]:
        return trig7[i] if 0 <= i < n7 else None

    def _val14(i: int) -> Optional[Number]:
        return trig14[i] if 0 <= i < n14 else None

    # (22) 7天扳機線在70以上向下轉折
    p7 = _val7(idx - 1)
    c7 = _val7(idx)
    if p7 is not None and c7 is not None and p7 >= 70.0 and c7 < p7:
        results.append(
            Signal(
                id="TRIGGER7_TURN_DOWN",
                date=target_date,
                level="warning",
                title="7天扳機線在70以上向下轉折了",
                summary="7天扳機線在 70 以上由升轉跌，短期趨勢可能接近尾聲。",
                details=(
                    "扳機線在 70 以上代表短期趨勢極為強勢，一旦在高位出現向下轉折，"
                    "通常暗示這一段趨勢可能接近告一段落，需要提防反轉或較大幅度的回調。"
                ),
            )
        )

    # (23) 14天扳機線在70以上向下轉折
    p14 = _val14(idx - 1)
    c14 = _val14(idx)
    if p14 is not None and c14 is not None and p14 >= 70.0 and c14 < p14:
        results.append(
            Signal(
                id="TRIGGER14_TURN_DOWN",
                date=target_date,
                level="warning",
                title="14天扳機線指標在70以上向下轉折了",
                summary="14天扳機線在 70 以上由升轉跌，中期趨勢可能接近尾聲。",
                details=(
                    "14天扳機線是較中期的趨勢指標，當其在 70 以上出現向下轉折時，"
                    "往往與較重要的頭部或趨勢結束時點相符合，需提高風險意識。"
                ),
            )
        )

    # (24) 7天扳機線半空中轉折
    # 過去8天以來曾符合(22)，當天扳機線上升且過去8天皆>=45。
    look_start = max(1, idx - 7)
    seen_22 = False
    for j in range(look_start, idx + 1):
        pj = _val7(j - 1)
        cj = _val7(j)
        if pj is not None and cj is not None and pj >= 70.0 and cj < pj:
            seen_22 = True
            break
    if seen_22 and p7 is not None and c7 is not None and c7 > p7:
        seg = [v for v in (trig7[look_start : idx + 1] if n7 > idx else []) if v is not None]
        if seg and min(seg) >= 45.0:
            results.append(
                Signal(
                    id="TRIGGER7_MID_AIR_TURN",
                    date=target_date,
                    level="warning",
                    title="7天扳機線指標出現了半空中轉折",
                    summary="先前在高檔出現轉折後，7天扳機線在 45 以上重新由跌轉升，趨勢可能再走一段。",
                    details=(
                        "文档描述，當扳機線在高位轉折後不久便在半空中掉頭回升，"
                        "往往代表這段趨勢尚未結束，後續仍可能再走出一段兇猛行情，"
                        "需要同時留意量價與其他趨勢指標的配合。"
                    ),
                )
            )

    return results


def detect_mid_direction_band_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (25)-(28) 中期方向線與變動式超買/超賣線的一度/二度撞擊。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return []

    mid = _mid_direction_series(bars)
    lower, upper = _dynamic_band(mid)
    n = len(mid)
    if n <= idx:
        return []

    results: List[Signal] = []

    def _val(series: Sequence[Optional[Number]], i: int) -> Optional[Number]:
        return series[i] if 0 <= i < len(series) else None

    m_prev = mid[idx - 1]
    m_curr = mid[idx]
    low_prev = _val(lower, idx - 1)
    low_curr = _val(lower, idx)
    up_prev = _val(upper, idx - 1)
    up_curr = _val(upper, idx)

    # (25) 一度向下撞擊變動式超賣線（中期方向線先跌破後再站回）
    if low_prev is not None and low_curr is not None and m_prev < low_prev and m_curr > low_curr:
        # 檢查過去30天是否未出現過相同條件
        start = max(1, idx - 30)
        seen = False
        for j in range(start, idx):
            lp = _val(lower, j - 1)
            lc = _val(lower, j)
            if lp is None or lc is None:
                continue
            if mid[j - 1] < lp and mid[j] > lc:
                seen = True
                break
        if not seen:
            results.append(
                Signal(
                    id="MIDDIR_HIT_LOWER_ONCE",
                    date=target_date,
                    level="info",
                    title="中期方向線向下撞擊了它的變動式超賣線",
                    summary="中期方向線先跌破變動式超賣線又站回，從機率上常在此附近止跌回升。",
                    details=(
                        "文档指出，當中期方向線向下撞擊變動式超賣線後再度站回之上，"
                        "從統計機率來看，行情在此附近止跌回升的機率較高，是重要的中期支撐信號之一。"
                    ),
                )
            )

    # (26) 一度向上撞擊變動式超買線
    if up_prev is not None and up_curr is not None and m_prev > up_prev and m_curr < up_curr:
        start = max(1, idx - 30)
        seen = False
        for j in range(start, idx):
            upj_prev = _val(upper, j - 1)
            upj_curr = _val(upper, j)
            if upj_prev is None or upj_curr is None:
                continue
            if mid[j - 1] > upj_prev and mid[j] < upj_curr:
                seen = True
                break
        if not seen:
            results.append(
                Signal(
                    id="MIDDIR_HIT_UPPER_ONCE",
                    date=target_date,
                    level="warning",
                    title="中期方向線向上撞擊了它的變動式超買線",
                    summary="中期方向線向上撞擊變動式超買線後回落，行情在此區域暫歇或回調的機率較高。",
                    details=(
                        "文档中提到，當中期方向線向上撞擊變動式超買線後又跌回線下，"
                        "從機率角度來看，行情在此價位附近暫時休息或回調的機率顯著提高。"
                    ),
                )
            )

    # (27) 二度向下撞擊變動式超賣線（在30天內已出現過(25)）
    if low_prev is not None and low_curr is not None and m_prev < low_prev and m_curr > low_curr:
        start = max(1, idx - 30)
        count = 0
        for j in range(start, idx):
            lp = _val(lower, j - 1)
            lc = _val(lower, j)
            if lp is None or lc is None:
                continue
            if mid[j - 1] < lp and mid[j] > lc:
                count += 1
        if count >= 1:
            results.append(
                Signal(
                    id="MIDDIR_HIT_LOWER_TWICE",
                    date=target_date,
                    level="info",
                    title="中期方向線二度向下撞擊變動式超賣線",
                    summary="中期方向線在短時間內兩度向下撞擊變動式超賣線，股價多處於相對低檔區。",
                    details=(
                        "文档指出，中期方向線向下二度撞擊變動式超賣線時，"
                        "通常代表股價已經處於相對低檔區域，止跌回升的機率大幅提高。"
                    ),
                )
            )

    # (28) 二度向上撞擊變動式超買線
    if up_prev is not None and up_curr is not None and m_prev > up_prev and m_curr < up_curr:
        start = max(1, idx - 30)
        count = 0
        for j in range(start, idx):
            upj_prev = _val(upper, j - 1)
            upj_curr = _val(upper, j)
            if upj_prev is None or upj_curr is None:
                continue
            if mid[j - 1] > upj_prev and mid[j] < upj_curr:
                count += 1
        if count >= 1:
            results.append(
                Signal(
                    id="MIDDIR_HIT_UPPER_TWICE",
                    date=target_date,
                    level="warning",
                    title="中期方向線二度向上撞擊變動式超買線",
                    summary="中期方向線在短時間內兩度向上撞擊變動式超買線，股價多處於相對高檔區。",
                    details=(
                        "文档指出，中期方向線向上二度撞擊變動式超買線時，"
                        "股價形成重要高點或頭部的機率明顯提高，需要特別留意風險。"
                    ),
                )
            )

    return results


def detect_mid_direction_shape_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (29)-(30) 中期方向線海灣/海島型態。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return []

    mid = _mid_direction_series(bars)
    n = len(mid)
    if n <= idx:
        return []

    results: List[Signal] = []

    # (29) 海灣型態：中期方向線短暫跌破0軸（<=0天數<=5），前一段連續>0天數>=30，當天重新>0
    if mid[idx - 1] <= 0.0 and mid[idx] > 0.0:
        neg_days = 0
        j = idx - 1
        while j >= 0 and mid[j] <= 0.0:
            neg_days += 1
            j -= 1
        pos_before = 0
        while j >= 0 and mid[j] > 0.0:
            pos_before += 1
            j -= 1
        if 1 <= neg_days <= 5 and pos_before >= 30:
            results.append(
                Signal(
                    id="MIDDIR_BAY",
                    date=target_date,
                    level="info",
                    title="中期方向線出現海灣型態",
                    summary="中期方向線在0軸上方長期為紅，短暫翻綠後又迅速站回紅色區域，類似海灣形態。",
                    details=(
                        "文档將此形態描述為兩座紅色山巒之間夾著一小塊綠色凹陷的海灣，"
                        "歷史經驗顯示，當中期方向線出現海灣型態時，股價由跌轉升的機率相當高。"
                    ),
                )
            )

    # (30) 海島型態：中期方向線短暫站上0軸（>=0天數<=5），前一段連續<0天數>=30，當天重新<0
    if mid[idx - 1] >= 0.0 and mid[idx] < 0.0:
        pos_days = 0
        j = idx - 1
        while j >= 0 and mid[j] >= 0.0:
            pos_days += 1
            j -= 1
        neg_before = 0
        while j >= 0 and mid[j] < 0.0:
            neg_before += 1
            j -= 1
        if 1 <= pos_days <= 5 and neg_before >= 30:
            results.append(
                Signal(
                    id="MIDDIR_ISLAND",
                    date=target_date,
                    level="warning",
                    title="中期方向線出現海島型態",
                    summary="中期方向線長期位於0軸下方，短暫翻紅後又迅速跌回綠色區域，類似海島型態。",
                    details=(
                        "文档中將此形態比喻為在大片綠色海洋中出現一小段紅色凸起的孤島，"
                        "往往象徵多頭誘多陷阱，行情可能由升轉跌，需要謹慎應對。"
                    ),
                )
            )

    return results


def detect_ma_cluster_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (31)-(32) 日指數平均線開始向上/向下聚集。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 2:
        return []

    closes = [b.close for b in bars]
    ema4 = ema(closes, 4)
    ema8 = ema(closes, 8)
    ema12 = ema(closes, 12)
    ema16 = ema(closes, 16)
    ema20 = ema(closes, 20)
    ema47 = ema(closes, 47)
    n = min(len(ema4), len(ema8), len(ema12), len(ema16), len(ema20), len(ema47))
    if idx >= n:
        return []

    vals = [ema4[idx], ema8[idx], ema12[idx], ema16[idx], ema20[idx], ema47[idx]]
    vmax = max(vals)
    vmin = min(vals)
    vmean = sum(vals) / len(vals)
    spread_pct = abs(vmax - vmin) / (abs(vmean) if vmean != 0 else 1e-9) * 100.0

    results: List[Signal] = []

    # 上下聚集判斷共用 spread_pct <= 0.75
    if spread_pct <= 0.75:
        # (31) 向上聚集：4日與8日EMA連續三天上升
        if (
            ema4[idx] > ema4[idx - 1] > ema4[idx - 2]
            and ema8[idx] > ema8[idx - 1] > ema8[idx - 2]
        ):
            results.append(
                Signal(
                    id="EMA_CLUSTER_UP",
                    date=target_date,
                    level="info",
                    title="日指數平均線開始向上聚集",
                    summary="多條短中期指數均線在極小區間內向上聚集，意味多空大軍正在高位集結。",
                    details=(
                        "文档指出，日指數平均線向上聚集代表多空大軍在高位集結，"
                        "往往是決戰前的前奏，後續可能出現出其不意的欺敵手法與劇烈波動。"
                    ),
                )
            )
        # (32) 向下聚集：4日與8日EMA連續三天下降
        if (
            ema4[idx] < ema4[idx - 1] < ema4[idx - 2]
            and ema8[idx] < ema8[idx - 1] < ema8[idx - 2]
        ):
            results.append(
                Signal(
                    id="EMA_CLUSTER_DOWN",
                    date=target_date,
                    level="warning",
                    title="日指數平均線開始向下聚集",
                    summary="多條短中期指數均線在極小區間內向下聚集，空頭力量可能正在集結。",
                    details=(
                        "文档指出，當所有平均線都向下聚集時，"
                        "市場通常預期股價將大幅下跌，但也要留意可能出現相反方向的突襲與震盪。"
                    ),
                )
            )

    return results


def detect_ma47_deviation_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (33)-(36) 股價與47日指數平均線的正/負乖離過大與極大化。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None:
        return []

    closes = [b.close for b in bars]
    ema4 = ema(closes, 4)
    ema47 = ema(closes, 47)
    n = min(len(ema4), len(ema47))
    if idx >= n:
        return []

    results: List[Signal] = []
    dev = (ema4[idx] - ema47[idx]) / (ema47[idx] if ema47[idx] != 0 else 1e-9) * 100.0

    # 導航圖：用中期方向線近似，平衡軸視為0
    mid = _mid_direction_series(bars)
    if idx >= len(mid):
        return []
    nav_prev = mid[idx - 1] if idx >= 1 else mid[idx]
    nav_curr = mid[idx]

    # (33) 正乖離太大 (7%~8%) 且導航圖由上轉下
    if 7.0 <= dev < 8.0 and nav_prev >= 0.0 and nav_curr < nav_prev:
        results.append(
            Signal(
                id="DEV47_POS_LARGE",
                date=target_date,
                level="warning",
                title="股價與47日指數平均線的正乖離太大了",
                summary="股價相對47日指數平均線上方乖離達到約7%~8%，隨時可能出現拉回。",
                details=(
                    "文档用被繩子拴住的牛來比喻股價與季線的距離，"
                    "當正乖離過大時，好比繩子已經被拉到極限，"
                    "股價隨時可能因乖離修正而拉回。"
                ),
            )
        )

    # (34) 正乖離極大化 (>=8%) 且導航圖由上轉下
    if dev >= 8.0 and nav_prev >= 0.0 and nav_curr < nav_prev:
        results.append(
            Signal(
                id="DEV47_POS_EXTREME",
                date=target_date,
                level="warning",
                title="股價與47日平均線的正乖離已經極大化了",
                summary="股價相對47日指數平均線正乖離超過約8%，回調風險極高。",
                details=(
                    "文档指出，在強勢行情中股價有時會把與47日平均線之間的繩子拉得更長，"
                    "一旦正乖離極大化，除非有足夠力量把繩子拉斷，"
                    "否則行情隨時可能出現劇烈拉回。"
                ),
            )
        )

    # (35) 負乖離太大 (7%~8%) 且導航圖由下轉上
    if -8.0 < dev <= -7.0 and nav_prev <= 0.0 and nav_curr > nav_prev:
        results.append(
            Signal(
                id="DEV47_NEG_LARGE",
                date=target_date,
                level="info",
                title="股價向下偏離季線技術性範圍了",
                summary="股價相對47日指數平均線向下偏離約7%~8%，技術性超跌，有機會止跌回升。",
                details=(
                    "文档中指出，股價向下偏離47天指數平均線達到一定距離時，"
                    "就像被繩子拉得太遠一樣，隨時有技術性反彈的可能。"
                ),
            )
        )

    # (36) 負乖離達到極限 (<=-8%) 且導航圖由下轉上
    if dev <= -8.0 and nav_prev <= 0.0 and nav_curr > nav_prev:
        results.append(
            Signal(
                id="DEV47_NEG_EXTREME",
                date=target_date,
                level="info",
                title="股價向下偏離季線的技術性達到極限了",
                summary="股價相對47日指數平均線向下偏離超過約8%，技術性超跌達到極限，反彈機率高。",
                details=(
                    "文档提到，當股價向下偏離季線的技術性達到極限時，"
                    "隨時都有出現強勢反彈的可能，需關注量能是否配合回升。"
                ),
            )
        )

    return results


def _band_cross_signals(
    series: Sequence[Optional[Number]],
    lower: Sequence[Optional[Number]],
    upper: Sequence[Optional[Number]],
    idx: int,
) -> Tuple[bool, bool]:
    """
    通用判斷：返回 (向下撞擊超賣線, 向上撞擊超買線)。
    """
    if idx < 1 or idx >= len(series):
        return False, False
    prev = series[idx - 1]
    curr = series[idx]
    low_prev = lower[idx - 1] if 0 <= idx - 1 < len(lower) else None
    low_curr = lower[idx] if 0 <= idx < len(lower) else None
    up_prev = upper[idx - 1] if 0 <= idx - 1 < len(upper) else None
    up_curr = upper[idx] if 0 <= idx < len(upper) else None
    hit_lower = (
        prev is not None
        and curr is not None
        and low_prev is not None
        and low_curr is not None
        and prev <= low_prev
        and curr > low_curr
    )
    hit_upper = (
        prev is not None
        and curr is not None
        and up_prev is not None
        and up_curr is not None
        and prev >= up_prev
        and curr < up_curr
    )
    return hit_lower, hit_upper


def detect_pvi_band_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (37)-(38) PVI 向下/向上撞擊變動式超賣/超買線。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None:
        return []
    pvi = _pvi_series(bars)
    lower, upper = _dynamic_band(pvi)
    hit_lower, hit_upper = _band_cross_signals(pvi, lower, upper, idx)
    results: List[Signal] = []
    if hit_lower:
        results.append(
            Signal(
                id="PVI_HIT_LOWER",
                date=target_date,
                level="info",
                title="PVI向下撞擊了它的變動式超賣線",
                summary="正量指標 PVI 向下撞擊變動式超賣線，量能有超賣跡象，行情易暫時止跌。",
                details=(
                    "文档指出，當 PVI 向下撞擊變動式超賣線時，"
                    "量能處於相對低迷區間，股價通常容易在此獲得支撐並暫時止跌。"
                ),
            )
        )
    if hit_upper:
        results.append(
            Signal(
                id="PVI_HIT_UPPER",
                date=target_date,
                level="warning",
                title="PVI向上撞擊了它的變動式超買線",
                summary="正量指標 PVI 向上撞擊變動式超買線，量能有超買跡象，行情容易遭遇壓力。",
                details=(
                    "文档指出，當 PVI 向上撞擊變動式超買線時，"
                    "量能處於相對過熱狀態，股價通常會遭遇較大壓力，"
                    "若同時股價也出現超買信號，信號可靠度將大幅提升。"
                ),
            )
        )
    return results


def detect_obv_band_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (39)-(42) OBV 及其2日EMA對變動式超買/超賣線的一度/二度撞擊。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None:
        return []
    obv = _obv_series(bars)
    obv_ema2 = ema(obv, 2)
    lower, upper = _dynamic_band(obv_ema2)
    hit_lower, hit_upper = _band_cross_signals(obv_ema2, lower, upper, idx)
    results: List[Signal] = []

    # (39) 一度向下撞擊變動式超賣線
    if hit_lower:
        results.append(
            Signal(
                id="OBV2_HIT_LOWER",
                date=target_date,
                level="info",
                title="OBV的2日指數平均線向下撞擊了它的變動式超賣線",
                summary="OBV 2日EMA 向下撞擊變動式超賣線，量能超賣，股價易獲得支撐。",
                details=(
                    "文档指出，當 OBV 能量潮向下撞擊其變動式超賣線時，"
                    "股價通常會獲得一定程度的支撐，至少會暫時止跌。"
                ),
            )
        )

    # (40) 一度向上撞擊變動式超買線
    if hit_upper:
        results.append(
            Signal(
                id="OBV2_HIT_UPPER",
                date=target_date,
                level="warning",
                title="OBV的2日指數平均線向上撞擊了它的變動式超買線",
                summary="OBV 2日EMA 向上撞擊變動式超買線，量能超買，行情易遭遇較大賣壓。",
                details=(
                    "文档指出，當 OBV 能量潮向上撞擊其變動式超買線時，"
                    "股價通常會遭遇明顯壓力，行情至少會暫時停歇或回調。"
                ),
            )
        )

    # (41) 二度向下撞擊變動式超賣線（20天內已出現過一次向下撞擊）
    if hit_lower:
        count = 0
        start = max(1, idx - 20)
        for j in range(start, idx):
            hl, _ = _band_cross_signals(obv_ema2, lower, upper, j)
            if hl:
                count += 1
        if count >= 1:
            results.append(
                Signal(
                    id="OBV2_HIT_LOWER_TWICE",
                    date=target_date,
                    level="info",
                    title="OBV的2日EMA向下二度撞擊變動式超賣線",
                    summary="OBV 2日EMA在短期內兩次向下撞擊變動式超賣線，股價在此止跌回升的機率極高。",
                    details=(
                        "文档指出，若 OBV 能量潮在短時間內兩度向下撞擊變動式超賣線，"
                        "至少有八成機率股價會在此區域止跌回升，是難得的買進參考信號。"
                    ),
                )
            )

    # (42) 二度向上撞擊變動式超買線
    if hit_upper:
        count = 0
        start = max(1, idx - 20)
        for j in range(start, idx):
            _, hu = _band_cross_signals(obv_ema2, lower, upper, j)
            if hu:
                count += 1
        if count >= 1:
            results.append(
                Signal(
                    id="OBV2_HIT_UPPER_TWICE",
                    date=target_date,
                    level="warning",
                    title="OBV的2日EMA向上二度撞擊變動式超買線",
                    summary="OBV 2日EMA在短期內兩次向上撞擊變動式超買線，是重要的賣出或調節信號。",
                    details=(
                        "文档指出，當 OBV 能量潮在短時間內連續兩次向上撞擊變動式超買線時，"
                        "往往是難得的賣出信號，至少需要適度調節手中持股。"
                    ),
                )
            )

    return results


def detect_dpo_band_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (43)-(44) DPO 向下/向上撞擊變動式超賣/超買線。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None:
        return []
    closes = [b.close for b in bars]
    dpo = _dpo_series(closes, period=20)
    lower, upper = _dynamic_band([x or 0.0 for x in dpo])
    hit_lower, hit_upper = _band_cross_signals(dpo, lower, upper, idx)
    results: List[Signal] = []
    if hit_lower:
        results.append(
            Signal(
                id="DPO_HIT_LOWER",
                date=target_date,
                level="info",
                title="DPO向下撞擊了變動式超賣線",
                summary="DPO 向下撞擊變動式超賣線，股價重心偏向低位，行情易在此穩住腳步。",
                details=(
                    "文档說明，DPO 用於描述股價重心，當 DPO 向下撞擊變動式超賣線時，"
                    "好比重心下移變得更穩固，行情在此附近形成短期穩定區的機率較高。"
                ),
            )
        )
    if hit_upper:
        results.append(
            Signal(
                id="DPO_HIT_UPPER",
                date=target_date,
                level="warning",
                title="DPO向上撞擊了變動式超買線",
                summary="DPO 向上撞擊變動式超買線，股價重心偏高，行情容易在此跌倒。",
                details=(
                    "文档將 DPO 向上撞擊變動式超買線比喻為頭重腳輕、重心不穩，"
                    "代表股價已經偏離平衡點過多，稍有風吹草動就可能出現回落。"
                ),
            )
        )
    return results


def detect_mom_band_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (45)-(46) MOM 向下/向上撞擊變動式超賣/超買線。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None:
        return []
    closes = [b.close for b in bars]
    mom = _mom_series(closes, period=10)
    lower, upper = _dynamic_band([x or 0.0 for x in mom])
    hit_lower, hit_upper = _band_cross_signals(mom, lower, upper, idx)
    results: List[Signal] = []
    if hit_lower:
        results.append(
            Signal(
                id="MOM_HIT_LOWER",
                date=target_date,
                level="info",
                title="MOM向下撞擊了變動式超賣線",
                summary="MOM 向下撞擊變動式超賣線，價格與平衡點的距離過大，有向上修正的機會。",
                details=(
                    "文档指出，MOM 描述股價相對平衡狀態的偏離，"
                    "當 MOM 向下撞擊變動式超賣線時，代表股價偏離平衡過多，"
                    "為了修正平衡，後續向上反彈的機率較高。"
                ),
            )
        )
    if hit_upper:
        results.append(
            Signal(
                id="MOM_HIT_UPPER",
                date=target_date,
                level="warning",
                title="MOM向上撞擊了變動式超買線",
                summary="MOM 向上撞擊變動式超買線，股價偏離平衡過多，向下修正的風險提高。",
                details=(
                    "文档指出，當 MOM 向上撞擊變動式超買線時，"
                    "股價與平衡點之間的距離超出了技術性範圍，"
                    "往往需要通過回調來修正這種失衡。"
                ),
            )
        )
    return results


def detect_emv_band_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (47)-(48) EMV 向下/向上撞擊變動式超賣/超買線。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None:
        return []
    emv = _emv_series(bars)
    lower, upper = _dynamic_band([x or 0.0 for x in emv])
    hit_lower, hit_upper = _band_cross_signals(emv, lower, upper, idx)
    results: List[Signal] = []
    if hit_lower:
        results.append(
            Signal(
                id="EMV_HIT_LOWER",
                date=target_date,
                level="info",
                title="EMV向下撞擊了變動式超賣線",
                summary="EMV 向下撞擊變動式超賣線，量能極度萎縮後有迴光返照的機會。",
                details=(
                    "文档指出，EMV 指標認為成交量過快放大會消耗行情能量，"
                    "當 EMV 向下撞擊變動式超賣線時，量能已萎縮到一定程度，"
                    "根據循環原理，行情有可能出現迴光返照。"
                ),
            )
        )
    if hit_upper:
        results.append(
            Signal(
                id="EMV_HIT_UPPER",
                date=target_date,
                level="warning",
                title="EMV向上撞擊了變動式超買線",
                summary="EMV 向上撞擊變動式超買線，成交量擴增至某一限度後，行情隨時可能回調。",
                details=(
                    "文档指出，當 EMV 向上撞擊變動式超買線時，"
                    "代表成交量擴增至某一限度，行情短期內容易出現回調或休息。"
                ),
            )
        )
    return results


def detect_price_gravity_band_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (49)-(50) 價差引力向下/向上撞擊變動式超賣/超買線。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None:
        return []
    pg = _price_gravity_series(bars)
    lower, upper = _dynamic_band(pg)
    hit_lower, hit_upper = _band_cross_signals(pg, lower, upper, idx)
    results: List[Signal] = []
    if hit_lower:
        results.append(
            Signal(
                id="PRICE_GRAVITY_HIT_LOWER",
                date=target_date,
                level="info",
                title="價差引力向下撞擊了變動式超賣線",
                summary="價差引力向下撞擊變動式超賣線，補足了其他指標漏接的低點。",
                details=(
                    "文档指出，價差引力指標經常能夠補足 MOM、DPO 甚至中期方向線漏接的低點，"
                    "當其向下撞擊變動式超賣線時，往往能捕捉到重要低點機會。"
                ),
            )
        )
    if hit_upper:
        results.append(
            Signal(
                id="PRICE_GRAVITY_HIT_UPPER",
                date=target_date,
                level="warning",
                title="價差引力向上撞擊了變動式超買線",
                summary="價差引力向上撞擊變動式超買線，補足了其他指標漏接的高點。",
                details=(
                    "文档指出，價差引力指標能夠抓住其他指標抓不到的高點，"
                    "當其向上撞擊變動式超買線時，常常是重要頭部或調節時機。"
                ),
            )
        )
    return results


def detect_vr_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (51)-(52) VR 指標的能量蓄水區與高水位區。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return []
    vr = _vr_series(bars)
    if len(vr) <= idx:
        return []
    prev = vr[idx - 1]
    curr = vr[idx]
    results: List[Signal] = []

    # (51) VR 由 >50 變 <=50
    if prev is not None and curr is not None and prev > 50.0 and curr <= 50.0:
        results.append(
            Signal(
                id="VR_ENTER_LOW_ENERGY",
                date=target_date,
                level="info",
                title="VR已經進入能量的蓄水區",
                summary="VR 從 50 以上跌至 50 以下，屬於能量蓄水區，保守買盤開始進場。",
                details=(
                    "文档提到，VR 在約 40~50 一帶時，代表消極性資金開始承接，"
                    "行情容易在此獲得支撐，雖不一定立刻反攻，但多頭可在此喘口氣。"
                ),
            )
        )

    # (52) VR 由 <250 變 >=250
    if prev is not None and curr is not None and prev < 250.0 and curr >= 250.0:
        results.append(
            Signal(
                id="VR_ABOVE_ALERT",
                date=target_date,
                level="warning",
                title="VR量能已越過250的警戒區",
                summary="VR 向上突破 250，量能過熱，短期內需提防高位風險。",
                details=(
                    "文档指出，當 VR 上升至 250 以上時，代表市場情緒與成交量極為熱絡，"
                    "短期內雖可能再拖行一段漲勢，但風險也同步大增，需要謹慎。"
                ),
            )
        )

    return results


def detect_cr_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (53)-(54) CR 指標的低水位區與高水位區。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return []
    cr = _cr_series(bars)
    if len(cr) <= idx:
        return []
    prev = cr[idx - 1]
    curr = cr[idx]
    results: List[Signal] = []

    # (53) CR 由 >50 變 <=50
    if prev is not None and curr is not None and prev > 50.0 and curr <= 50.0:
        results.append(
            Signal(
                id="CR_ENTER_LOW",
                date=target_date,
                level="info",
                title="近期CR數值已降至低水位區",
                summary="CR 從 50 以上跌至 50 以下，行情有機會在此醞釀底部。",
                details=(
                    "文档指出，當 CR 指標下降到接近 40 或 50 一帶時，"
                    "行情形成中長期谷底的機率偏高，後續容易出現反彈。"
                ),
            )
        )

    # (54) CR 由 <250 變 >=250
    if prev is not None and curr is not None and prev < 250.0 and curr >= 250.0:
        results.append(
            Signal(
                id="CR_HIGH_LEVEL",
                date=target_date,
                level="warning",
                title="近期CR數值大幅陡升至高水位區",
                summary="CR 數值躍升至 250 以上，量價結構偏熱，可能接近相對高點區。",
                details=(
                    "文档指出，CR 用於輔助觀察底部與高位，當 CR 升至 250 或更高時，"
                    "若同時 VR 也處於高檔，代表量價均熱過頭，高點風險較大。"
                ),
            )
        )

    return results


def detect_br_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (55)-(56) BR 情緒指標的悲觀與過嗨訊號。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return []
    br, _ar = _br_ar_series(bars)
    if len(br) <= idx:
        return []
    prev = br[idx - 1]
    curr = br[idx]
    results: List[Signal] = []

    # (55) BR 由 >50 變 <=50
    if prev is not None and curr is not None and prev > 50.0 and curr <= 50.0:
        results.append(
            Signal(
                id="BR_PESSIMISM",
                date=target_date,
                level="info",
                title="BR顯示最近市場情緒似乎過於悲觀",
                summary="BR 從 50 以上跌至 50 以下，反市場心理下往往是底部醞釀區。",
                details=(
                    "文档引用 BR 群眾情緒比例表指出，當 BR 下降到 40~50 附近時，"
                    "代表市場上看壞行情的人明顯多於看好者，反市場心理下，"
                    "往往更接近中長期低點區。"
                ),
            )
        )

    # (56) BR 由 <250 變 >=250
    if prev is not None and curr is not None and prev < 250.0 and curr >= 250.0:
        results.append(
            Signal(
                id="BR_OVER_EXCITED",
                date=target_date,
                level="warning",
                title="BR情緒指標警示近期股民情緒有點兒太嗨了",
                summary="BR 升至 250 以上，群眾情緒過度樂觀，容易引發獲利回吐。",
                details=(
                    "文档指出，當 BR 升至 250 甚至 300 以上時，"
                    "代表大多數市場參與者對後市過度樂觀，"
                    "往往容易引發獲利回吐與較大賣壓。"
                ),
            )
        )

    return results


def detect_ar_signals(bars: Sequence[DailyBar], target_date: date) -> List[Signal]:
    """
    (57)-(58) AR 指標的能量累積與過度消耗。
    """
    idx = _find_index_by_date(bars, target_date)
    if idx is None or idx < 1:
        return []
    _br, ar = _br_ar_series(bars)
    if len(ar) <= idx:
        return []
    prev = ar[idx - 1]
    curr = ar[idx]
    results: List[Signal] = []

    # (57) AR 由 >50 變 <=50
    if prev is not None and curr is not None and prev > 50.0 and curr <= 50.0:
        results.append(
            Signal(
                id="AR_ENERGY_ACCUMULATE",
                date=target_date,
                level="info",
                title="這一陣子AR指標顯示能量開始重新積累",
                summary="AR 從 50 以上跌至 50 以下，資金回流股民口袋，未來買盤能量開始累積。",
                details=(
                    "文档指出，當 AR 下跌到 50 或 40 以下時，"
                    "代表推升股價所花費的金額減少，資金回流股民手中，"
                    "隨時有機會重新進場買股票，行情具備能量蓄積條件。"
                ),
            )
        )

    # (58) AR 由 <180 變 >=180
    if prev is not None and curr is not None and prev < 180.0 and curr >= 180.0:
        results.append(
            Signal(
                id="AR_OVER_SPENT",
                date=target_date,
                level="warning",
                title="AR指標預警短期內成交量消耗過度",
                summary="AR 升至 180 以上，推升股價所花的錢太多，後續上漲空間有限。",
                details=(
                    "文档指出，當 AR 超過 180 時，代表市場裡為推升股價已經花費大量資金，"
                    "可投入的增量資金有限，行情向下反轉的機率明顯增加。"
                ),
            )
        )

    return results


def detect_all_signals(
    bars: Sequence[DailyBar],
    target_date: date,
) -> List[Dict[str, Any]]:
    """
    聚合檢測所有已實現的代表性信號，返回可直接序列化為 JSON 的列表。
    """
    detectors = [
        detect_kd_down_gap,
        detect_kd_up_gap,
        detect_macd_up_reaction,
        detect_macd_down_reaction,
        detect_macd_bull_divergence,
        detect_macd_bear_divergence,
        detect_macd_zero_cross_down,
        detect_macd_zero_cross_up,
        detect_cci_upper_turn,
        detect_cci_lower_turn,
    ]
    results: List[Dict[str, Any]] = []
    for fn in detectors:
        sig = fn(bars, target_date)
        if sig:
            results.append(sig.to_json())

    # 多個信號組返回列表
    for sig in detect_qiu_tiandi_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_ultimate_osc_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_trigger_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_mid_direction_band_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_mid_direction_shape_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_ma_cluster_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_ma47_deviation_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_pvi_band_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_obv_band_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_dpo_band_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_mom_band_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_emv_band_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_price_gravity_band_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_vr_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_cr_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_br_signals(bars, target_date):
        results.append(sig.to_json())
    for sig in detect_ar_signals(bars, target_date):
        results.append(sig.to_json())
    return results


__all__ = [
    "Signal",
    "detect_kd_down_gap",
    "detect_kd_up_gap",
    "detect_macd_up_reaction",
    "detect_macd_down_reaction",
    "detect_macd_bull_divergence",
    "detect_macd_bear_divergence",
    "detect_macd_zero_cross_down",
    "detect_macd_zero_cross_up",
    "detect_cci_upper_turn",
    "detect_cci_lower_turn",
    "detect_qiu_tiandi_signals",
    "detect_ultimate_osc_signals",
    "detect_trigger_signals",
    "detect_mid_direction_band_signals",
    "detect_mid_direction_shape_signals",
    "detect_ma_cluster_signals",
    "detect_ma47_deviation_signals",
    "detect_pvi_band_signals",
    "detect_obv_band_signals",
    "detect_dpo_band_signals",
    "detect_mom_band_signals",
    "detect_emv_band_signals",
    "detect_price_gravity_band_signals",
    "detect_vr_signals",
    "detect_cr_signals",
    "detect_br_signals",
    "detect_ar_signals",
    "detect_all_signals",
]

