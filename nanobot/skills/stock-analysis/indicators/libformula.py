from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import importlib
import json
import os
import shutil
import sys
import zipfile
from contextlib import contextmanager

# 添加 stock-analysis 目录到路径以支持导入
SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from http_client import DailyBar
from storage import get_base_dir

INDICATOR_NAME_ALIASES = {
    "DIRECT": "DIR",
}

ALL_LIBFORMULA_INDICATOR_NAMES = (
    "K", "LK", "BAR", "PCK", "PK", "EXP", "CAN", "EQU", "TBL", "TOW", "OX", "NSZ",
    "TP", "ARMS", "ABI", "ADR", "ADL", "BTI", "MCL", "MSI", "OBOS", "STIX", "VOL", "AMO",
    "Y", "H", "R", "BBI", "KD", "SKD", "MACD", "DMA", "W", "MOM", "DPO", "ROC", "OSC",
    "CCI", "UDL", "UOS", "DMI", "SAR", "OBV", "BOLL", "ENE", "MIKE", "TRIX", "VCI", "MAR",
    "BRAR", "CR", "VR", "EMV", "WVAD", "PVI", "NVI", "TAPI", "PSY", "PCNT", "CSI", "VHF",
    "MASS", "MFI", "MONEY", "QIUV", "QIUSV", "XTD", "QIUQ", "XE", "XF", "XK", "XVF", "DIR",
    "DIR2", "JC", "RAD", "QIUS", "TRIG", "TRIG2", "PD", "XT", "XN", "XEV", "XWV", "SAT",
    "LJJ", "VBOLL", "BB", "WID", "FIRE", "DED", "XA", "XB", "XC", "XD", "KT1", "KT2", "CDP",
)

ADVANCED_INDICATOR_NAMES = ("XK", "DIR", "JC", "SAT", "PD", "SAR", "DED", "XVF")

ASSETS_DIR = SKILL_ROOT / "assets"
JAR_PATH = ASSETS_DIR / "finance-indicator-openapi.jar"
NATIVE_LIB_PATH = ASSETS_DIR / "libformula.so"
FORMULA_FILE_PATH = ASSETS_DIR / "xxss_encrypt.mov"


class LibformulaError(RuntimeError):
    """Base error for libformula bridge failures."""


class AssetNotFoundError(LibformulaError):
    """Required runtime asset is missing."""


class JVMStartupError(LibformulaError):
    """JVM or JPype could not be initialized."""


class FormulaExecutionError(LibformulaError):
    """Java formula call failed."""


class IndicatorResultError(LibformulaError):
    """Formula returned no usable value for target date."""


@dataclass(frozen=True)
class _RuntimeAssets:
    jar_path: Path
    native_lib_path: Path
    formula_file_path: Path


@dataclass(frozen=True)
class LinePoint:
    trade_date: date
    value: float | None


@dataclass(frozen=True)
class KLinePoint:
    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None
    color: float | None = None
    hop: float | None = None
    lop: float | None = None


@dataclass(frozen=True)
class LineSeriesResult:
    indicator_name: str
    series: dict[str, list[LinePoint]]
    meta: dict[str, Any]


@dataclass(frozen=True)
class KLineSeriesResult:
    indicator_name: str
    kline_name: str
    points: list[KLinePoint]
    overlays: dict[str, list[LinePoint]]
    meta: dict[str, Any]


@dataclass(frozen=True)
class SpecialSeriesResult:
    indicator_name: str
    payload: dict[str, Any]


class _LibformulaRuntime:
    _shared: "_LibformulaRuntime | None" = None

    def __init__(self) -> None:
        self.assets = _resolve_assets()
        self.jpype = _load_jpype()
        self.runtime_dir = _ensure_formula_runtime_dir(self.assets.formula_file_path)
        self._ensure_jvm()
        self.ArrayList = self.jpype.JClass("java.util.ArrayList")
        self.HashMap = self.jpype.JClass("java.util.LinkedHashMap")
        self.OHLCVData = self.jpype.JClass("com.linlong.ssa.base.core.charts.entity.OHLCVData")
        try:
            self.IndicatorFacade = self.jpype.JClass("com.linlong.cloud.service.IndicatorFacade")
            self.IndicatorMetadataRegistry = self.jpype.JClass("com.linlong.cloud.service.IndicatorMetadataRegistry")
        except Exception as exc:  # pragma: no cover - requires runtime jar
            raise JVMStartupError(
                "当前 finance-indicator-openapi.jar 未包含新的 IndicatorFacade/IndicatorMetadataRegistry 类，请先构建最新 jar。"
            ) from exc
        with _temporary_cwd(self.runtime_dir):
            self.facade = self.IndicatorFacade(str(self.assets.formula_file_path), False)
        self._metadata_cache: dict[str, dict[str, Any]] | None = None

    @classmethod
    def shared(cls) -> "_LibformulaRuntime":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def _ensure_jvm(self) -> None:
        classpath = _build_classpath(self.assets.jar_path)
        logback_config = _ensure_quiet_logback_config()
        if self.jpype.isJVMStarted():
            return
        jvm_args = [
            f"-Djava.library.path={self.assets.native_lib_path.parent}",
            f"-Dlogback.configurationFile={logback_config}",
        ]
        try:
            self.jpype.startJVM(*jvm_args, classpath=classpath, convertStrings=True)
        except Exception as exc:
            raise JVMStartupError(f"启动 JVM 失败: {exc}") from exc

    def metadata_map(self) -> dict[str, dict[str, Any]]:
        if self._metadata_cache is None:
            raw = str(self.IndicatorMetadataRegistry.metadataJson())
            payload = json.loads(raw)
            self._metadata_cache = {str(item["hotKey"]).upper(): item for item in payload}
        return self._metadata_cache

    def run_indicator_payload(
        self,
        stock_code: str,
        bars: list[DailyBar],
        indicator_name: str,
        index_bars: list[DailyBar] | None = None,
        param_overrides: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            with _temporary_cwd(self.runtime_dir):
                raw_result = self.facade.calculate(
                    _normalize_indicator_name(indicator_name),
                    stock_code,
                    self._to_java_ohlcv_list(bars),
                    None if index_bars is None else self._to_java_ohlcv_list(index_bars),
                    self._to_java_map(param_overrides or {}),
                    "",
                )
        except Exception as exc:
            raise FormulaExecutionError(f"{indicator_name} 计算失败: {exc}") from exc

        payload = _convert_java_value(raw_result)
        if not isinstance(payload, dict):
            raise FormulaExecutionError(f"{indicator_name} 返回结果格式异常: {payload!r}")
        return payload

    def run_indicator(
        self,
        stock_code: str,
        bars: list[DailyBar],
        target_date: date,
        indicator_name: str,
        index_bars: list[DailyBar] | None = None,
        param_overrides: dict[str, str] | None = None,
    ) -> Any:
        payload = self.run_indicator_payload(
            stock_code=stock_code,
            bars=bars,
            indicator_name=indicator_name,
            index_bars=index_bars,
            param_overrides=param_overrides,
        )
        return _extract_indicator_value(indicator_name, payload, target_date)

    def _to_java_ohlcv_list(self, bars: Iterable[DailyBar]) -> Any:
        java_list = self.ArrayList()
        for bar in bars:
            java_list.add(
                self.OHLCVData(
                    _date_to_yyyymmdd(bar.trade_date),
                    float(bar.open),
                    float(bar.high),
                    float(bar.low),
                    float(bar.close),
                    float(bar.vol),
                    float(bar.amount),
                )
            )
        return java_list

    def _to_java_map(self, payload: dict[str, str]) -> Any:
        java_map = self.HashMap()
        for key, value in payload.items():
            java_map.put(str(key), str(value))
        return java_map


def compute_advanced_indicators(
    bars: list[DailyBar],
    target_date: date,
    stock_code: str | None = None,
    market_index_bars: list[DailyBar] | None = None,
) -> dict[str, Any]:
    return compute_libformula_indicators(
        bars=bars,
        target_date=target_date,
        indicator_names=ADVANCED_INDICATOR_NAMES,
        stock_code=stock_code,
        market_index_bars=market_index_bars,
    )


def compute_libformula_indicator_payloads(
    bars: list[DailyBar],
    indicator_names: Iterable[str],
    stock_code: str | None = None,
    market_index_bars: list[DailyBar] | None = None,
    param_overrides: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, Any]]:
    if not bars:
        raise ValueError("bars 不能为空")
    runtime = _LibformulaRuntime.shared()
    resolved_stock_code = _infer_stock_code(stock_code or bars[0].ts_code)
    payloads: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for indicator_name in indicator_names:
        normalized_name = _normalize_indicator_name(indicator_name)
        if normalized_name in seen:
            continue
        seen.add(normalized_name)
        payloads[indicator_name] = runtime.run_indicator_payload(
            stock_code=resolved_stock_code,
            bars=bars,
            indicator_name=normalized_name,
            index_bars=market_index_bars,
            param_overrides=(param_overrides or {}).get(normalized_name)
            or (param_overrides or {}).get(indicator_name),
        )
    return payloads


def compute_libformula_indicators(
    bars: list[DailyBar],
    target_date: date,
    indicator_names: Iterable[str],
    stock_code: str | None = None,
    market_index_bars: list[DailyBar] | None = None,
    param_overrides: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not bars:
        raise ValueError("bars 不能为空")
    runtime = _LibformulaRuntime.shared()
    resolved_stock_code = _infer_stock_code(stock_code or bars[0].ts_code)
    indicators: dict[str, Any] = {}
    seen: set[str] = set()
    for indicator_name in indicator_names:
        normalized_name = _normalize_indicator_name(indicator_name)
        if normalized_name in seen:
            continue
        seen.add(normalized_name)
        indicators[indicator_name] = runtime.run_indicator(
            stock_code=resolved_stock_code,
            bars=bars,
            target_date=target_date,
            indicator_name=normalized_name,
            index_bars=market_index_bars,
            param_overrides=(param_overrides or {}).get(normalized_name)
            or (param_overrides or {}).get(indicator_name),
        )
    return indicators


def build_indicator_result_models(payloads: dict[str, dict[str, Any]]) -> dict[str, LineSeriesResult | KLineSeriesResult | SpecialSeriesResult]:
    return {name: build_indicator_result_model(name, payload) for name, payload in payloads.items()}


def build_indicator_result_model(
    indicator_name: str,
    payload: dict[str, Any],
) -> LineSeriesResult | KLineSeriesResult | SpecialSeriesResult:
    if not isinstance(payload, dict) or not payload.get("supported", False):
        return SpecialSeriesResult(indicator_name=indicator_name, payload=payload)

    series_list = payload.get("series") or []
    kline_series = next((item for item in series_list if item.get("type") == "kline"), None)
    meta = {
        key: value
        for key, value in payload.items()
        if key not in {"series"}
    }
    if kline_series:
        points: list[KLinePoint] = []
        for point in kline_series.get("points") or []:
            trade_date = _coerce_to_date(point.get("time"))
            if trade_date is None:
                continue
            points.append(
                KLinePoint(
                    trade_date=trade_date,
                    open=_coerce_float(point.get("open")),
                    high=_coerce_float(point.get("high")),
                    low=_coerce_float(point.get("low")),
                    close=_coerce_float(point.get("close")),
                    volume=_coerce_float(point.get("volume")),
                    amount=_coerce_float(point.get("amount")),
                    color=_coerce_float(point.get("color")),
                    hop=_coerce_float(point.get("hop")),
                    lop=_coerce_float(point.get("lop")),
                )
            )
        overlays: dict[str, list[LinePoint]] = {}
        for item in series_list:
            if item is kline_series:
                continue
            overlays[str(item.get("name") or "series")] = _series_points_to_line_points(item)
        return KLineSeriesResult(
            indicator_name=indicator_name,
            kline_name=str(kline_series.get("name") or "kline"),
            points=points,
            overlays=overlays,
            meta=meta,
        )

    return LineSeriesResult(
        indicator_name=indicator_name,
        series={
            str(item.get("name") or "series"): _series_points_to_line_points(item)
            for item in series_list
        },
        meta=meta,
    )


def indicator_metadata() -> dict[str, dict[str, Any]]:
    return dict(_LibformulaRuntime.shared().metadata_map())


def _resolve_assets() -> _RuntimeAssets:
    for path in (JAR_PATH, NATIVE_LIB_PATH, FORMULA_FILE_PATH):
        if not path.is_file():
            raise AssetNotFoundError(f"libformula 资源文件缺失: {path}")
    return _RuntimeAssets(
        jar_path=JAR_PATH,
        native_lib_path=NATIVE_LIB_PATH,
        formula_file_path=FORMULA_FILE_PATH,
    )


def _load_jpype() -> Any:
    try:
        return importlib.import_module("jpype")
    except ModuleNotFoundError as exc:
        raise JVMStartupError("缺少依赖 jpype1，请先安装项目依赖后再运行 indicators") from exc


def _build_classpath(jar_path: Path) -> list[str]:
    extracted_root = _extract_fat_jar(jar_path)
    classes_dir = extracted_root / "BOOT-INF" / "classes"
    if not classes_dir.is_dir():
        raise JVMStartupError(f"JAR 解包后未找到 classes 目录: {classes_dir}")
    classpath = [str(classes_dir)]
    lib_dir = extracted_root / "BOOT-INF" / "lib"
    if lib_dir.is_dir():
        classpath.extend(str(path) for path in sorted(lib_dir.glob("*.jar")))
    return classpath


def _extract_fat_jar(jar_path: Path) -> Path:
    cache_key = f"{jar_path.stem}-{jar_path.stat().st_size}-{jar_path.stat().st_mtime_ns}"
    target_dir = get_base_dir() / "libformula-jvm" / cache_key
    marker = target_dir / ".ready"
    if marker.is_file():
        return target_dir

    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(jar_path) as zf:
            zf.extractall(target_dir)
    except Exception as exc:
        raise JVMStartupError(f"解包 libformula JAR 失败: {exc}") from exc

    marker.write_text("ok", encoding="utf-8")
    return target_dir


def _ensure_formula_runtime_dir(formula_file_path: Path) -> Path:
    runtime_dir = get_base_dir() / "libformula-runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    target = runtime_dir / formula_file_path.name
    if not target.exists():
        try:
            target.symlink_to(formula_file_path)
        except OSError:
            shutil.copy2(formula_file_path, target)
    return runtime_dir


@contextmanager
def _temporary_cwd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _ensure_quiet_logback_config() -> Path:
    path = get_base_dir() / "libformula-jvm" / "logback-silent.xml"
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <root level="OFF" />
</configuration>
""",
        encoding="utf-8",
    )
    return path


def _normalize_indicator_name(indicator_name: str) -> str:
    normalized = str(indicator_name).strip().upper()
    if not normalized:
        raise ValueError("指标名不能为空")
    return INDICATOR_NAME_ALIASES.get(normalized, normalized)


def _infer_stock_code(ts_code: str) -> str:
    if "." not in ts_code:
        text = ts_code.strip().upper()
        if len(text) > 2 and text[:2] in {"SH", "SZ", "BJ", "GZ"}:
            return text[2:]
        return text
    symbol, _exchange = ts_code.split(".", 1)
    return symbol


def _date_to_yyyymmdd(value: date) -> int:
    return int(value.strftime("%Y%m%d"))


def _convert_java_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple, dict)):
        if isinstance(value, dict):
            return {str(k): _convert_java_value(v) for k, v in value.items()}
        return [_convert_java_value(item) for item in value]

    class_name = str(type(value))
    if "java.lang.String" in class_name:
        return str(value)
    if "java.util.Date" in class_name:
        try:
            return datetime.fromtimestamp(value.getTime() / 1000, tz=timezone.utc).date().isoformat()
        except Exception:
            return str(value)

    if _is_java_map(value):
        return {str(entry.getKey()): _convert_java_value(entry.getValue()) for entry in value.entrySet()}
    if _is_java_iterable(value):
        return [_convert_java_value(item) for item in value]

    if hasattr(value, "getClass"):
        bean = _convert_java_bean(value)
        if bean:
            return bean
    return str(value)


def _is_java_iterable(value: Any) -> bool:
    return hasattr(value, "__iter__") and hasattr(value, "getClass")


def _is_java_map(value: Any) -> bool:
    return hasattr(value, "entrySet") and hasattr(value, "getClass")


def _convert_java_bean(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        methods = value.getClass().getMethods()
    except Exception:
        return result

    for method in methods:
        try:
            if method.getParameterCount() != 0:
                continue
            name = method.getName()
            if name == "getClass":
                continue
            if name.startswith("get") and len(name) > 3:
                key = name[3:4].lower() + name[4:]
            elif name.startswith("is") and len(name) > 2:
                key = name[2:3].lower() + name[3:]
            else:
                continue
            result[key] = _convert_java_value(method.invoke(value))
        except Exception:
            continue
    return result


# B 类指标（需重建 K 线/特殊结构），与 docs/INDICATOR_EXTRACTION_CS.md 一致
B_CLASS_INDICATORS = frozenset(
    {"K", "LK", "BAR", "PCK", "XK", "PD", "SAR", "DED", "CAN", "EQU", "VOL", "AMO", "KT1", "KT2"}
)


def _extract_xk_color(raw_result: Any, target_date: date) -> int | None:
    """XK 指标：取 kline 系列在目标日或最后一根的 color，规范为 1~4。与 C# GetXKPlotElement 一致。"""
    if not isinstance(raw_result, dict):
        return None
    series_list = raw_result.get("series") or []
    kline_series = next((s for s in series_list if isinstance(s, dict) and s.get("type") == "kline"), None)
    if not kline_series:
        return None
    points = kline_series.get("points") or []
    point = None
    for p in points:
        if not isinstance(p, dict):
            continue
        pt_date = _coerce_to_date(p.get("time"))
        if pt_date == target_date:
            point = p
            break
    if point is None and points:
        for p in reversed(points):
            if isinstance(p, dict) and _coerce_to_date(p.get("time")) is not None:
                point = p
                break
    if point is None:
        return None
    color = point.get("color")
    if color is None:
        return None
    try:
        v = int(round(float(color)))
        return max(1, min(4, v))
    except (TypeError, ValueError):
        return None


def _extract_indicator_value(indicator_name: str, raw_result: Any, target_date: date) -> Any:
    if isinstance(raw_result, dict) and raw_result.get("supported") is False:
        raise IndicatorResultError(
            f"{indicator_name} 当前在不可修改 JNI 约束下不支持: {raw_result.get('reason') or '未知原因'}"
        )

    # XK：仅返回 COLOR 标量 1~4，与 C# 一致
    if indicator_name == "XK":
        color = _extract_xk_color(raw_result, target_date)
        if color is not None:
            return float(color)

    matched = _extract_from_series_payload(indicator_name, raw_result, target_date)
    if matched is not None:
        return matched

    raise IndicatorResultError(f"{indicator_name} 在 {target_date.isoformat()} 未返回可用结果")


def _extract_from_series_payload(
    indicator_name: str, raw_result: Any, target_date: date
) -> Any:
    if not isinstance(raw_result, dict):
        return None
    series_list = raw_result.get("series")
    if not isinstance(series_list, list) or not series_list:
        return None

    # 目标日无匹配时使用最后一根有效 bar（与 C# 文档「当前值」一致）
    use_last = True
    values: dict[str, Any] = {}
    for item in series_list:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("type") or "series")
        points = item.get("points")
        if not isinstance(points, list):
            continue
        matched = _match_series_point(points, target_date, use_last_if_no_match=use_last)
        if matched is None:
            continue
        values[name] = matched
    if not values:
        return None
    # 单曲线返回标量，多曲线返回 { name: value }
    if len(values) == 1:
        return next(iter(values.values()))
    return values


def _match_series_point(
    points: list[Any], target_date: date, use_last_if_no_match: bool = False
) -> Any:
    found = None
    last_valid = None
    for point in points:
        if not isinstance(point, dict):
            continue
        point_date = _coerce_to_date(point.get("time"))
        if point_date is not None:
            last_valid = point
        if point_date != target_date:
            continue
        payload = {k: v for k, v in point.items() if k != "time" and v is not None}
        if not payload:
            found = point
        elif list(payload.keys()) == ["value"]:
            found = payload["value"]
        else:
            found = payload
        break
    if found is not None:
        return found
    if use_last_if_no_match and last_valid is not None:
        payload = {k: v for k, v in last_valid.items() if k != "time" and v is not None}
        if not payload:
            return last_valid
        if list(payload.keys()) == ["value"]:
            return payload["value"]
        return payload
    return None


def _series_points_to_line_points(series: dict[str, Any]) -> list[LinePoint]:
    result: list[LinePoint] = []
    for point in series.get("points") or []:
        trade_date = _coerce_to_date(point.get("time"))
        if trade_date is None:
            continue
        result.append(LinePoint(trade_date=trade_date, value=_coerce_float(point.get("value"))))
    return result


def _coerce_to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (int, float)):
        if 10_000_000 <= int(value) <= 99_999_999:
            text = str(int(value))
            try:
                return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:8]}")
            except ValueError:
                return None
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).date()
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if len(text) == 8 and text.isdigit():
            try:
                return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:8]}")
            except ValueError:
                return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ADVANCED_INDICATOR_NAMES",
    "ALL_LIBFORMULA_INDICATOR_NAMES",
    "AssetNotFoundError",
    "FormulaExecutionError",
    "IndicatorResultError",
    "JVMStartupError",
    "KLinePoint",
    "KLineSeriesResult",
    "LibformulaError",
    "LinePoint",
    "LineSeriesResult",
    "SpecialSeriesResult",
    "build_indicator_result_model",
    "build_indicator_result_models",
    "compute_advanced_indicators",
    "compute_libformula_indicator_payloads",
    "compute_libformula_indicators",
    "indicator_metadata",
]
