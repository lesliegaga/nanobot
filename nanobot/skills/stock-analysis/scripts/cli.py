from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

# 将 skill 根目录加入 sys.path，便于导入同目录下的模块
HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from http_client import (  # type: ignore[import]
    DailyBar,
    StockApiError,
    get_stock_basic,
    get_stock_daily_fq,
    get_stock_snapshot,
)
from indicators.ta import compute_all_indicators  # type: ignore[import]
from indicators import signals as signal_mod  # type: ignore[import]


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _print_error(code: str, message: str) -> None:
    _print_json({"ok": False, "error": {"code": code, "message": message}})


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"无效日期格式: {value}，应为 YYYY-MM-DD") from exc


def _bars_to_json(bars: List[DailyBar]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for b in bars:
        result.append(
            {
                "ts_code": b.ts_code,
                "trade_date": b.trade_date.isoformat(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "pre_close": b.pre_close,
                "change": b.change,
                "pct_chg": b.pct_chg,
                "vol": b.vol,
                "amount": b.amount,
            }
        )
    return result


def cmd_basic(args: argparse.Namespace) -> None:
    try:
        items = get_stock_basic(
            full_code=args.full_code,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        _print_json(
            {
                "ok": True,
                "type": "basic",
                "fullCode": args.full_code,
                "items": items,
            }
        )
    except StockApiError as exc:
        _print_error("HTTP_ERROR", str(exc))


def cmd_daily(args: argparse.Namespace) -> None:
    try:
        bars = get_stock_daily_fq(
            full_code=args.full_code,
            start_date=args.start_date,
            count=args.count,
            end_date=args.end_date,
        )
        _print_json(
            {
                "ok": True,
                "type": "daily",
                "fullCode": args.full_code,
                "bars": _bars_to_json(bars),
            }
        )
    except (StockApiError, ValueError) as exc:
        _print_error("HTTP_ERROR", str(exc))


def cmd_indicators(args: argparse.Namespace) -> None:
    try:
        # 使用目标日期作为 start_date，API 会向前获取 lookback 条数据
        bars = get_stock_daily_fq(
            full_code=args.full_code,
            start_date=args.date.isoformat(),
            count=args.lookback,
            end_date=args.end_date,
        )
        if not bars:
            _print_error("NO_DATA", "未获取到任何日K数据")
            return

        target = args.date
        result = compute_all_indicators(bars, target)
        _print_json(
            {
                "ok": True,
                "type": "indicators",
                "fullCode": args.full_code,
                "date": target.isoformat(),
                "price": result["price"],
                "indicators": result["indicators"],
            }
        )
    except ValueError as exc:
        _print_error("NO_DATA", str(exc))
    except StockApiError as exc:
        _print_error("HTTP_ERROR", str(exc))


def cmd_signals(args: argparse.Namespace) -> None:
    try:
        # 使用目标日期作为 start_date，API 会向前获取 lookback 条数据
        bars = get_stock_daily_fq(
            full_code=args.full_code,
            start_date=args.date.isoformat(),
            count=args.lookback,
            end_date=args.end_date,
        )
        if not bars:
            _print_error("NO_DATA", "未获取到任何日K数据")
            return

        target = args.date
        sigs = signal_mod.detect_all_signals(bars, target)
        _print_json(
            {
                "ok": True,
                "type": "signals",
                "fullCode": args.full_code,
                "date": target.isoformat(),
                "signals": sigs,
            }
        )
    except ValueError as exc:
        _print_error("NO_DATA", str(exc))
    except StockApiError as exc:
        _print_error("HTTP_ERROR", str(exc))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stock analysis skill CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # basic
    p_basic = subparsers.add_parser("basic", help="查询股票基础信息")
    p_basic.add_argument("--full-code", dest="full_code", type=str, default=None, help="证券 fullCode，如 SH600000")
    p_basic.add_argument("--start-date", type=str, default=None, help="起始日期 (YYYY-MM-DD)")
    p_basic.add_argument("--end-date", type=str, default=None, help="结束日期 (YYYY-MM-DD)")
    p_basic.set_defaults(func=cmd_basic)

    # daily
    p_daily = subparsers.add_parser("daily", help="查询单只股票前复权日K数据")
    p_daily.add_argument("--full-code", dest="full_code", type=str, required=True, help="证券 fullCode，如 SH600000")
    p_daily.add_argument("--start-date", type=str, required=True, help="起始日期 (YYYY-MM-DD)")
    p_daily.add_argument("--end-date", type=str, default=None, help="结束日期 (预留，可为空)")
    p_daily.add_argument("--count", type=int, required=True, help="向前获取的K线条数，包含 startDate 当日")
    p_daily.set_defaults(func=cmd_daily)

    # indicators
    p_ind = subparsers.add_parser("indicators", help="计算指定日期的技术指标")
    p_ind.add_argument("--full-code", dest="full_code", type=str, required=True, help="证券 fullCode，如 SH600000")
    p_ind.add_argument("--date", type=_parse_date, required=True, help="目标交易日 (YYYY-MM-DD)")
    p_ind.add_argument("--start-date", type=str, required=True, help="日K 查询起始日期 (YYYY-MM-DD)")
    p_ind.add_argument("--end-date", type=str, default=None, help="结束日期 (预留，可为空)")
    p_ind.add_argument(
        "--lookback",
        type=int,
        default=120,
        help="向前获取的日K条数，用于计算长周期指标，默认 120",
    )
    p_ind.set_defaults(func=cmd_indicators)

    # signals
    p_sig = subparsers.add_parser("signals", help="识别指定日期的高级技术信号")
    p_sig.add_argument("--full-code", dest="full_code", type=str, required=True, help="证券 fullCode，如 SH600000")
    p_sig.add_argument("--date", type=_parse_date, required=True, help="目标交易日 (YYYY-MM-DD)")
    p_sig.add_argument("--start-date", type=str, required=True, help="日K 查询起始日期 (YYYY-MM-DD)")
    p_sig.add_argument("--end-date", type=str, default=None, help="结束日期 (预留，可为空)")
    p_sig.add_argument(
        "--lookback",
        type=int,
        default=160,
        help="向前获取的日K条数，用于识别形态，默认 160",
    )
    p_sig.set_defaults(func=cmd_signals)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if not func:
        parser.print_help()
        sys.exit(1)
    func(args)


if __name__ == "__main__":
    main()

