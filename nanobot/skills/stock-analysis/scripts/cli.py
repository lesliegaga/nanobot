from __future__ import annotations

import argparse
import json
import os
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
from storage import save_json  # type: ignore[import]


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


def _bars_from_json(items: List[Dict[str, Any]]) -> List[DailyBar]:
    """
    将 cmd_daily 输出的 bars JSON 结构还原为 DailyBar 列表。
    """
    bars: List[DailyBar] = []
    for row in items:
        try:
            trade_date_val = date.fromisoformat(str(row["trade_date"]))
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
    # 保持与 HTTP 查询一致的按 trade_date 从旧到新排序
    bars.sort(key=lambda b: b.trade_date)
    return bars


def _resolve_output_path(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _maybe_cache_and_print(
    kind: str,
    key_parts: Dict[str, Any],
    payload: Dict[str, Any],
    summary: Dict[str, Any],
    output_file: str | None,
) -> None:
    """
    统一处理输出逻辑：
    - 若指定 output_file，则写入该文件，只打印 summary（附 filePath）；
    - 否则将结果写入缓存目录（若未配置环境变量则使用默认 .cache 目录），在 summary 中补充 cacheRef 与 filePath。
    """
    if output_file:
        path = _resolve_output_path(output_file)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        summary = dict(summary)
        summary["filePath"] = str(path)
        _print_json(summary)
        return

    # 自动缓存：默认使用 storage.get_base_dir() 返回的目录
    ref_id, cache_path = save_json(kind, key_parts, payload)
    summary = dict(summary)
    summary["cacheRef"] = ref_id
    summary["filePath"] = str(cache_path)
    _print_json(summary)


def cmd_basic(args: argparse.Namespace) -> None:
    try:
        items = get_stock_basic(
            full_code=args.full_code,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        payload = {
            "ok": True,
            "type": "basic",
            "fullCode": args.full_code,
            "items": items,
        }
        summary = {
            "ok": True,
            "type": "basic",
            "fullCode": args.full_code,
            "itemCount": len(items),
        }
        key_parts: Dict[str, Any] = {
            "fullCode": args.full_code or "ALL",
            "startDate": args.start_date or "",
            "endDate": args.end_date or "",
        }
        _maybe_cache_and_print("basic", key_parts, payload, summary, getattr(args, "output_file", None))
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
        bars_json = _bars_to_json(bars)
        payload = {
            "ok": True,
            "type": "daily",
            "fullCode": args.full_code,
            "bars": bars_json,
        }
        summary = {
            "ok": True,
            "type": "daily",
            "fullCode": args.full_code,
            "rowCount": len(bars_json),
        }
        key_parts: Dict[str, Any] = {
            "fullCode": args.full_code,
            "startDate": args.start_date,
            "endDate": args.end_date or "",
            "count": args.count,
        }
        _maybe_cache_and_print("daily", key_parts, payload, summary, getattr(args, "output_file", None))
    except (StockApiError, ValueError) as exc:
        _print_error("HTTP_ERROR", str(exc))


def cmd_indicators(args: argparse.Namespace) -> None:
    try:
        # 优先从本地 daily 结果文件加载日 K 数据，避免重复 HTTP 请求
        bars: List[DailyBar]
        if getattr(args, "daily_file", None):
            daily_path = Path(args.daily_file).expanduser()
            if not daily_path.is_file():
                _print_error("NO_DATA", f"daily 文件不存在: {daily_path}")
                return
            with daily_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get("type") != "daily":
                _print_error("NO_DATA", f"daily 文件格式不正确: {daily_path}")
                return
            items = data.get("bars") or []
            if not isinstance(items, list):
                _print_error("NO_DATA", f"daily 文件中 bars 字段格式不正确: {daily_path}")
                return
            bars = _bars_from_json(items)
        else:
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
        payload = {
            "ok": True,
            "type": "indicators",
            "fullCode": args.full_code,
            "date": target.isoformat(),
            "price": result["price"],
            "indicators": result["indicators"],
        }
        indicators = result.get("indicators") or {}
        summary = {
            "ok": True,
            "type": "indicators",
            "fullCode": args.full_code,
            "date": target.isoformat(),
            "indicatorCount": len(indicators),
        }
        key_parts: Dict[str, Any] = {
            "fullCode": args.full_code,
            "date": target.isoformat(),
            "lookback": args.lookback,
            "endDate": args.end_date or "",
        }
        _maybe_cache_and_print("indicators", key_parts, payload, summary, getattr(args, "output_file", None))
    except ValueError as exc:
        _print_error("NO_DATA", str(exc))
    except StockApiError as exc:
        _print_error("HTTP_ERROR", str(exc))


def cmd_signals(args: argparse.Namespace) -> None:
    try:
        # 优先从本地 daily 结果文件加载日 K 数据，避免重复 HTTP 请求
        bars: List[DailyBar]
        if getattr(args, "daily_file", None):
            daily_path = Path(args.daily_file).expanduser()
            if not daily_path.is_file():
                _print_error("NO_DATA", f"daily 文件不存在: {daily_path}")
                return
            with daily_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get("type") != "daily":
                _print_error("NO_DATA", f"daily 文件格式不正确: {daily_path}")
                return
            items = data.get("bars") or []
            if not isinstance(items, list):
                _print_error("NO_DATA", f"daily 文件中 bars 字段格式不正确: {daily_path}")
                return
            bars = _bars_from_json(items)
        else:
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
        payload = {
            "ok": True,
            "type": "signals",
            "fullCode": args.full_code,
            "date": target.isoformat(),
            "signals": sigs,
        }
        summary = {
            "ok": True,
            "type": "signals",
            "fullCode": args.full_code,
            "date": target.isoformat(),
            "signalCount": len(sigs),
        }
        key_parts: Dict[str, Any] = {
            "fullCode": args.full_code,
            "date": target.isoformat(),
            "lookback": args.lookback,
            "endDate": args.end_date or "",
        }
        _maybe_cache_and_print("signals", key_parts, payload, summary, getattr(args, "output_file", None))
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
    p_basic.add_argument(
        "--output-file",
        dest="output_file",
        type=str,
        default=None,
        help="将完整结果写入指定 JSON 文件，仅在 stdout 输出轻量摘要",
    )
    p_basic.set_defaults(func=cmd_basic)

    # daily
    p_daily = subparsers.add_parser("daily", help="查询单只股票前复权日K数据")
    p_daily.add_argument("--full-code", dest="full_code", type=str, required=True, help="证券 fullCode，如 SH600000")
    p_daily.add_argument("--start-date", type=str, required=True, help="起始日期 (YYYY-MM-DD)")
    p_daily.add_argument("--end-date", type=str, default=None, help="结束日期 (预留，可为空)")
    p_daily.add_argument("--count", type=int, required=True, help="向前获取的K线条数，包含 startDate 当日")
    p_daily.add_argument(
        "--output-file",
        dest="output_file",
        type=str,
        default=None,
        help="将完整结果写入指定 JSON 文件，仅在 stdout 输出轻量摘要",
    )
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
    p_ind.add_argument(
        "--daily-file",
        dest="daily_file",
        type=str,
        default=None,
        help="从本地 daily JSON 文件加载日K数据，替代 HTTP 请求",
    )
    p_ind.add_argument(
        "--output-file",
        dest="output_file",
        type=str,
        default=None,
        help="将完整结果写入指定 JSON 文件，仅在 stdout 输出轻量摘要",
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
    p_sig.add_argument(
        "--daily-file",
        dest="daily_file",
        type=str,
        default=None,
        help="从本地 daily JSON 文件加载日K数据，替代 HTTP 请求",
    )
    p_sig.add_argument(
        "--output-file",
        dest="output_file",
        type=str,
        default=None,
        help="将完整结果写入指定 JSON 文件，仅在 stdout 输出轻量摘要",
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

