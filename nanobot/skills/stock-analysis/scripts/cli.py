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
    get_latest_trade_date,
)
from indicators.libformula import (  # type: ignore[import]
    AssetNotFoundError,
    FormulaExecutionError,
    IndicatorResultError,
    JVMStartupError,
    compute_advanced_indicators,
)
from indicators.ta import compute_all_indicators  # type: ignore[import]
from indicators import signals as signal_mod  # type: ignore[import]
from storage import save_json  # type: ignore[import]


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _print_error(code: str, message: str) -> None:
    _print_json({"ok": False, "error": {"code": code, "message": message}})


def _print_libformula_error(exc: Exception) -> None:
    if isinstance(exc, AssetNotFoundError):
        _print_error("LIBFORMULA_ASSET_MISSING", str(exc))
        return
    if isinstance(exc, JVMStartupError):
        _print_error("LIBFORMULA_JVM_ERROR", str(exc))
        return
    if isinstance(exc, IndicatorResultError):
        _print_error("LIBFORMULA_NO_RESULT", str(exc))
        return
    if isinstance(exc, FormulaExecutionError):
        _print_error("LIBFORMULA_RUN_ERROR", str(exc))
        return
    _print_error("LIBFORMULA_ERROR", str(exc))


def _validate_full_code(full_code: str, allow_all: bool = False) -> None:
    """
    校验 full_code 为 SH/SZ/BJ/GZ 前缀格式（如 SH600000）。
    CLI 仅支持该格式，不支持 600000.SH 等。
    """
    text = (full_code or "").strip().upper()
    if not text:
        raise ValueError("full_code 不能为空")
    if allow_all and text == "ALL":
        return
    if text.startswith(("SH", "SZ", "BJ", "GZ")) and len(text) > 2 and text[2:].isdigit():
        return
    if "." in text or (len(text) > 2 and not text.startswith(("SH", "SZ", "BJ", "GZ"))):
        raise ValueError(
            f"full_code 须为 SH/SZ/BJ/GZ+数字格式（如 SH600000），当前不支持 600000.SH 等形式：{full_code!r}"
        )
    raise ValueError(f"full_code 格式无效，应为如 SH600000：{full_code!r}")


def _market_index_full_code(full_code: str) -> str | None:
    text = (full_code or "").upper()
    if text.startswith("SH"):
        return "SH000001"
    if text.startswith("SZ"):
        return "SZ399001"
    if text.startswith("BJ"):
        return "BJ000002"
    if text.startswith("GZ"):
        return "GZ899001"
    return None


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"无效日期格式：{value}，应为 YYYY-MM-DD") from exc


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


def _maybe_cache_and_print(
    kind: str,
    key_parts: Dict[str, Any],
    payload: Dict[str, Any],
    summary: Dict[str, Any],
) -> None:
    """
    统一处理输出逻辑：
    - 否则将结果写入缓存目录（若未配置环境变量则使用默认 .cache 目录），在 summary 中补充 cacheRef 与 filePath。
    """
    # 自动缓存：默认使用 storage.get_base_dir() 返回的目录
    ref_id, cache_path = save_json(kind, key_parts, payload)
    summary = dict(summary)
    summary["cacheRef"] = ref_id
    summary["filePath"] = str(cache_path)
    _print_json(summary)


def cmd_basic(args: argparse.Namespace) -> None:
    try:
        _validate_full_code(args.full_code, allow_all=True)
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
        _maybe_cache_and_print("basic", key_parts, payload, summary)
    except StockApiError as exc:
        _print_error("HTTP_ERROR", str(exc))


def cmd_daily(args: argparse.Namespace) -> None:
    try:
        _validate_full_code(args.full_code)
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
        _maybe_cache_and_print("daily", key_parts, payload, summary)
    except (StockApiError, ValueError) as exc:
        _print_error("HTTP_ERROR", str(exc))


def cmd_indicators(args: argparse.Namespace) -> None:
    try:
        _validate_full_code(args.full_code)
        # 优先从本地 daily 结果文件加载日 K 数据，避免重复 HTTP 请求
        bars: List[DailyBar]
        if getattr(args, "daily_file", None):
            daily_path = Path(args.daily_file).expanduser()
            if not daily_path.is_file():
                _print_error("NO_DATA", f"daily 文件不存在：{daily_path}")
                return
            with daily_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get("type") != "daily":
                _print_error("NO_DATA", f"daily 文件格式不正确：{daily_path}")
                return
            items = data.get("bars") or []
            if not isinstance(items, list):
                _print_error("NO_DATA", f"daily 文件中 bars 字段格式不正确：{daily_path}")
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
            _print_error("NO_DATA", "未获取到任何日 K 数据")
            return

        target = args.date
        # 大盘指数 K 线：JC 等 SIMPLE_INDEX 指标必需，通过 get_stock_daily_fq 拉取
        market_index_bars: List[DailyBar] | None = None
        index_full_code = _market_index_full_code(args.full_code)
        if index_full_code:
            market_index_bars = get_stock_daily_fq(
                full_code=index_full_code,
                start_date=args.date.isoformat(),
                count=args.lookback,
                end_date=args.end_date,
            )
        result = compute_all_indicators(bars, target)
        advanced_indicators = compute_advanced_indicators(
            bars,
            target,
            stock_code=args.full_code,
            market_index_bars=market_index_bars,
        )
        result["indicators"].update(advanced_indicators)
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
        _maybe_cache_and_print("indicators", key_parts, payload, summary)
    except ValueError as exc:
        _print_error("NO_DATA", str(exc))
    except StockApiError as exc:
        _print_error("HTTP_ERROR", str(exc))
    except (AssetNotFoundError, JVMStartupError, IndicatorResultError, FormulaExecutionError) as exc:
        _print_libformula_error(exc)


def cmd_signals(args: argparse.Namespace) -> None:
    try:
        _validate_full_code(args.full_code)
        # 优先从本地 daily 结果文件加载日 K 数据，避免重复 HTTP 请求
        bars: List[DailyBar]
        if getattr(args, "daily_file", None):
            daily_path = Path(args.daily_file).expanduser()
            if not daily_path.is_file():
                _print_error("NO_DATA", f"daily 文件不存在：{daily_path}")
                return
            with daily_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get("type") != "daily":
                _print_error("NO_DATA", f"daily 文件格式不正确：{daily_path}")
                return
            items = data.get("bars") or []
            if not isinstance(items, list):
                _print_error("NO_DATA", f"daily 文件中 bars 字段格式不正确：{daily_path}")
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
            _print_error("NO_DATA", "未获取到任何日 K 数据")
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
        _maybe_cache_and_print("signals", key_parts, payload, summary)
    except ValueError as exc:
        _print_error("NO_DATA", str(exc))
    except StockApiError as exc:
        _print_error("HTTP_ERROR", str(exc))


def cmd_snapshot(args: argparse.Namespace) -> None:
    """查询股票最新实时快照数据"""
    try:
        _validate_full_code(args.full_code)
        items = get_stock_snapshot(full_code=args.full_code)
        if not items:
            _print_error("NO_DATA", "未获取到快照数据")
            return
        payload = {
            "ok": True,
            "type": "snapshot",
            "fullCode": args.full_code,
            "items": items,
        }
        summary = {
            "ok": True,
            "type": "snapshot",
            "fullCode": args.full_code,
            "itemCount": len(items),
        }
        key_parts: Dict[str, Any] = {
            "fullCode": args.full_code,
        }
        _maybe_cache_and_print("snapshot", key_parts, payload, summary)
    except (StockApiError, ValueError) as exc:
        _print_error("HTTP_ERROR", str(exc))


def cmd_latest_date(args: argparse.Namespace) -> None:
    """获取股票最新交易日期"""
    try:
        _validate_full_code(args.full_code)
        latest_date = get_latest_trade_date(args.full_code)
        if not latest_date:
            _print_error("NO_DATA", "未获取到最新交易日期")
            return
        payload = {
            "ok": True,
            "type": "latest-date",
            "fullCode": args.full_code,
            "tradeDate": latest_date.isoformat(),
        }
        _print_json(payload)
    except (StockApiError, ValueError) as exc:
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
    p_daily = subparsers.add_parser("daily", help="查询单只股票前复权日 K 数据")
    p_daily.add_argument("--full-code", dest="full_code", type=str, required=True, help="证券 fullCode，如 SH600000")
    p_daily.add_argument("--end-date", type=str, required=True, help="结束日期 (YYYY-MM-DD)")
    p_daily.add_argument("--start-date", type=str, default=None, help="起始日期 (预留，可为空)")
    p_daily.add_argument("--count", type=int, required=True, help="向前获取的 K 线条数，包含 endDate 当日")
    p_daily.set_defaults(func=cmd_daily)

    # indicators
    p_ind = subparsers.add_parser("indicators", help="计算指定日期的技术指标")
    p_ind.add_argument("--full-code", dest="full_code", type=str, required=True, help="证券 fullCode，仅支持 SH/SZ/BJ/GZ+数字，如 SH600000（不支持 600000.SH）")
    p_ind.add_argument("--date", type=_parse_date, required=True, help="目标交易日 (YYYY-MM-DD)")
    p_ind.add_argument("--end-date", type=str, required=True, help="日 K 查询结束日期 (YYYY-MM-DD)")
    p_ind.add_argument("--start-date", type=str, default=None, help="起始日期 (预留，可为空)")
    p_ind.add_argument(
        "--lookback",
        type=int,
        default=120,
        help="向前获取的日 K 条数，用于计算长周期指标，默认 120",
    )
    p_ind.add_argument(
        "--daily-file",
        dest="daily_file",
        type=str,
        default=None,
        help="从本地 daily JSON 文件加载日 K 数据，替代 HTTP 请求",
    )
    p_ind.set_defaults(func=cmd_indicators)

    # signals
    p_sig = subparsers.add_parser("signals", help="识别指定日期的高级技术信号")
    p_sig.add_argument("--full-code", dest="full_code", type=str, required=True, help="证券 fullCode，如 SH600000")
    p_sig.add_argument("--date", type=_parse_date, required=True, help="目标交易日 (YYYY-MM-DD)")
    p_sig.add_argument("--end-date", type=str, required=True, help="日 K 查询结束日期 (YYYY-MM-DD)")
    p_sig.add_argument("--start-date", type=str, default=None, help="起始日期 (预留，可为空)")
    p_sig.add_argument(
        "--lookback",
        type=int,
        default=160,
        help="向前获取的日 K 条数，用于识别形态，默认 160",
    )
    p_sig.add_argument(
        "--daily-file",
        dest="daily_file",
        type=str,
        default=None,
        help="从本地 daily JSON 文件加载日 K 数据，替代 HTTP 请求",
    )
    p_sig.set_defaults(func=cmd_signals)

    # snapshot
    p_snapshot = subparsers.add_parser("snapshot", help="查询股票最新实时快照")
    p_snapshot.add_argument("--full-code", dest="full_code", type=str, required=True, help="证券 fullCode，如 SH600000")
    p_snapshot.set_defaults(func=cmd_snapshot)

    # latest-date
    p_latest = subparsers.add_parser("latest-date", help="获取股票最新交易日期")
    p_latest.add_argument("--full-code", dest="full_code", type=str, required=True, help="证券 fullCode，如 SH600000")
    p_latest.set_defaults(func=cmd_latest_date)

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
