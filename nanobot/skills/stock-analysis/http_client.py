from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import os

import httpx


DEFAULT_BASE_URL = "http://uat-nbai-gw.caizidao.com.cn/business/security/api"


def _get_base_url() -> str:
    """
    Get stock API base URL from env or fallback to default.
    """
    return os.environ.get("STOCK_API_BASE", DEFAULT_BASE_URL).rstrip("/")


class StockApiError(RuntimeError):
    pass


def _post_json(path: str, payload: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
    """
    POST JSON to the stock API and return parsed JSON, raising StockApiError on failure.
    """
    base = _get_base_url()
    url = f"{base}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise StockApiError(f"HTTP 请求失败: {exc}") from exc

    if resp.status_code != 200:
        raise StockApiError(f"HTTP 状态码异常: {resp.status_code} {resp.text}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise StockApiError(f"响应不是合法 JSON: {resp.text[:200]}") from exc

    if data.get("code") != 1000:
        raise StockApiError(f"接口返回错误代码: {data.get('code')} 消息: {data.get('message')}")

    return data


def _normalize_table(content: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize Tushare-style {fields: [...], items: [[...], ...]} to list[dict].
    """
    fields = content.get("fields") or []
    items = content.get("items") or []
    result: List[Dict[str, Any]] = []
    for row in items:
        row_dict = {}
        for idx, field in enumerate(fields):
            if idx < len(row):
                row_dict[field] = row[idx]
        result.append(row_dict)
    return result


def get_stock_basic(
    full_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    获取股票基础信息（Tushare stock_basic 风格）。

    当 full_code 为空时，返回当日全量。
    """
    payload: Dict[str, Any] = {}
    if full_code:
        payload["fullCode"] = full_code
    if start_date:
        payload["startDate"] = start_date
    if end_date:
        payload["endDate"] = end_date

    data = _post_json("stock/basic", payload)
    content = data.get("content") or {}
    return _normalize_table(content)


def get_stock_snapshot(full_code: str) -> List[Dict[str, Any]]:
    """
    查询单只股票最新实时快照。
    """
    if not full_code:
        raise ValueError("full_code 不能为空")

    payload = {"fullCode": full_code}
    data = _post_json("stock/snapshot", payload)
    content = data.get("content") or {}
    return _normalize_table(content)


def get_latest_trade_date(full_code: str) -> date | None:
    """
    获取单只股票的最新交易日期。
    通过 snapshot 接口获取，返回最新交易日 date 对象，若无数据返回 None。
    """
    try:
        snapshot = get_stock_snapshot(full_code)
        if not snapshot:
            return None
        # snapshot 中包含 trade_time 字段 (格式：2026-03-09 16:59:54)
        row = snapshot[0]
        trade_time_str = str(row.get("trade_time", ""))
        if not trade_time_str:
            return None
        # 从 trade_time 中提取日期部分
        trade_date_str = trade_time_str.split(" ")[0]
        return date.fromisoformat(trade_date_str)
    except Exception:
        return None


@dataclass
class DailyBar:
    ts_code: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    pre_close: float
    change: float
    pct_chg: float
    vol: float
    amount: float


def get_stock_daily_fq(
    full_code: str,
    end_date: str,
    count: int,
    start_date: Optional[str] = None,
) -> List[DailyBar]:
    """
    查询单只股票前复权日 K 线（类似 Tushare daily，单票）。

    返回按 trade_date 从旧到新排序的 DailyBar 列表。
    """
    if not full_code:
        raise ValueError("full_code 不能为空")
    if not end_date:
        raise ValueError("end_date 不能为空")
    if count <= 0:
        raise ValueError("count 必须为正整数")

    # 接口约定：日 K 基于 endDate 向前取 count 天；仅传 endDate+count。
    payload: Dict[str, Any] = {
        "fullCode": full_code,
        "endDate": end_date,
        "count": count,
    }
    if start_date:
        payload["startDate"] = start_date

    data = _post_json("stock/daily/fq", payload)
    content = data.get("content") or {}
    rows = _normalize_table(content)

    bars: List[DailyBar] = []
    for row in rows:
        try:
            trade_date_str = str(row["trade_date"])
            trade_date_val = date.fromisoformat(trade_date_str)
            bars.append(
                DailyBar(
                    ts_code=str(row.get("ts_code", "")),
                    trade_date=trade_date_val,
                    open=float(row.get("open", 0.0)),
                    high=float(row.get("high", 0.0)),
                    low=float(row.get("low", 0.0)),
                    close=float(row.get("close", 0.0)),
                    pre_close=float(row.get("pre_close", 0.0)),
                    change=float(row.get("change", 0.0)),
                    pct_chg=float(row.get("pct_chg", 0.0)),
                    vol=float(row.get("vol", 0.0)),
                    amount=float(row.get("amount", 0.0)),
                )
            )
        except Exception:
            # 忽略单行解析错误
            continue

    bars.sort(key=lambda b: b.trade_date)
    return bars

