from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import importlib
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


ADVANCED_INDICATOR_NAMES = ("XK", "DIR", "JC", "SAT")
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


class _LibformulaRuntime:
    _shared: "_LibformulaRuntime | None" = None

    def __init__(self) -> None:
        self.assets = _resolve_assets()
        self.jpype = _load_jpype()
        self.runtime_dir = _ensure_formula_runtime_dir(self.assets.formula_file_path)
        self._ensure_jvm()
        self.ArrayList = self.jpype.JClass("java.util.ArrayList")
        self.Date = self.jpype.JClass("java.util.Date")
        self.OHLCVData = self.jpype.JClass("com.linlong.ssa.base.core.charts.entity.OHLCVData")
        self.Param = self.jpype.JClass("com.linlong.ssa.base.platform.jni.Param")
        self.Call = self.jpype.JClass("com.linlong.ssa.base.platform.jni.Call")
        with _temporary_cwd(self.runtime_dir):
            self.call = self.Call.getInstance(str(self.assets.formula_file_path), False)

    @classmethod
    def shared(cls) -> "_LibformulaRuntime":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def _ensure_jvm(self) -> None:
        classpath = _build_classpath(self.assets.jar_path)
        logback_config = _ensure_quiet_logback_config()
        if self.jpype.isJVMStarted():
            try:
                self.jpype.JClass("com.linlong.ssa.base.platform.jni.Call")
            except Exception as exc:  # pragma: no cover - requires externally started JVM
                raise JVMStartupError(
                    "JVM 已启动，但未包含 libformula 所需 classpath，无法加载 Call 类"
                ) from exc
            return

        jvm_args = [
            f"-Djava.library.path={self.assets.native_lib_path.parent}",
            f"-Dlogback.configurationFile={logback_config}",
        ]
        try:
            self.jpype.startJVM(*jvm_args, classpath=classpath, convertStrings=True)
        except Exception as exc:
            raise JVMStartupError(f"启动 JVM 失败: {exc}") from exc

    def run_indicator(
        self,
        stock_code: str,
        bars: list[DailyBar],
        target_date: date,
        indicator_name: str,
        index_bars: list[DailyBar] | None = None,
    ) -> Any:
        try:
            raw_result = self.call.run(
                stock_code,
                self._to_java_ohlcv_list(bars),
                None if index_bars is None else self._to_java_ohlcv_list(index_bars),
                _formula_name_for_indicator(indicator_name),
                self._to_java_param_list(indicator_name),
                "",
                _is_index_required(indicator_name),
            )
        except Exception as exc:
            raise FormulaExecutionError(f"{indicator_name} 计算失败: {exc}") from exc

        normalized = _convert_java_value(raw_result)
        return _extract_indicator_value(indicator_name, normalized, target_date)

    def _to_java_ohlcv_list(self, bars: Iterable[DailyBar]) -> Any:
        java_list = self.ArrayList()
        for bar in bars:
            java_list.add(
                self.OHLCVData(
                    _date_to_epoch_millis(bar.trade_date),
                    float(bar.open),
                    float(bar.high),
                    float(bar.low),
                    float(bar.close),
                    float(bar.vol),
                    float(bar.amount),
                )
            )
        return java_list

    def _to_java_param_list(self, indicator_name: str) -> Any:
        java_list = self.ArrayList()
        for name, value in _default_params_for_indicator(indicator_name).items():
            java_list.add(self.Param(str(name), str(value)))
        return java_list


def compute_advanced_indicators(
    bars: list[DailyBar],
    target_date: date,
    stock_code: str | None = None,
    market_index_bars: list[DailyBar] | None = None,
) -> dict[str, Any]:
    if not bars:
        raise ValueError("bars 不能为空")
    runtime = _LibformulaRuntime.shared()
    resolved_stock_code = _infer_stock_code(stock_code or bars[0].ts_code)
    indicators: dict[str, Any] = {}
    for indicator_name in ADVANCED_INDICATOR_NAMES:
        indicators[indicator_name] = runtime.run_indicator(
            stock_code=resolved_stock_code,
            bars=bars,
            target_date=target_date,
            indicator_name=indicator_name,
            index_bars=market_index_bars,
        )
    return indicators


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


def _default_params_for_indicator(indicator_name: str) -> dict[str, str]:
    mapping = {
        "XK": {
            "SYS_1": "12",
            "SYS_2": "47",
        },
        "DIR": {
            "SYS_1": "20",
            "SYS_2": "1.96",
            "SYS_3": "1.96",
        },
        "JC": {
            "SYS_1": "20",
            "Z_UPPER": "1.96",
            "Z_LOWER": "1.96",
        },
        "SAT": {
            "SYS_1": "15",
        },
    }
    try:
        return mapping[indicator_name]
    except KeyError as exc:
        raise ValueError(f"不支持的高级指标: {indicator_name}") from exc


def _formula_name_for_indicator(indicator_name: str) -> str:
    return {"DIR": "DIRECT"}.get(indicator_name, indicator_name)


def _is_index_required(indicator_name: str) -> int:
    return 1 if indicator_name == "JC" else 0


def _infer_stock_code(ts_code: str) -> str:
    if "." not in ts_code:
        text = ts_code.strip().upper()
        if len(text) > 2 and text[:2] in {"SH", "SZ", "BJ", "GZ"}:
            return text[2:]
        return text
    symbol, _exchange = ts_code.split(".", 1)
    return symbol


def _date_to_epoch_millis(value: date) -> int:
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


def _extract_indicator_value(indicator_name: str, raw_result: Any, target_date: date) -> Any:
    matched = _extract_from_response_rows(raw_result, target_date)
    if matched is not None:
        return matched

    matched = _extract_from_plot_elements(raw_result, target_date, indicator_name)
    if matched is not None:
        return matched

    raise IndicatorResultError(f"{indicator_name} 在 {target_date.isoformat()} 未返回可用结果")


def _extract_from_response_rows(raw_result: Any, target_date: date) -> Any:
    if not isinstance(raw_result, list) or not raw_result:
        return None
    if not all(isinstance(item, dict) and "timestamp" in item for item in raw_result):
        return None

    matches = [item for item in raw_result if _coerce_to_date(item.get("timestamp")) == target_date]
    if not matches:
        return None

    values: dict[str, Any] = {}
    for index, item in enumerate(matches):
        name = str(item.get("name") or f"item{index + 1}")
        payload = {
            key: value
            for key, value in item.items()
            if key not in {"name", "timestamp"} and value is not None
        }
        if list(payload.keys()) == ["value"]:
            values[name] = payload["value"]
        else:
            values[name] = payload

    if len(values) == 1:
        return next(iter(values.values()))
    return values


def _extract_from_plot_elements(raw_result: Any, target_date: date, indicator_name: str) -> Any:
    if not isinstance(raw_result, list) or not raw_result:
        return None
    if not all(isinstance(item, dict) and "data" in item for item in raw_result):
        return None

    values: dict[str, Any] = {}
    for index, item in enumerate(raw_result):
        series_name = str(item.get("name") or item.get("type") or f"{indicator_name}_{index + 1}")
        data_points = item.get("data")
        if not isinstance(data_points, list):
            continue
        matched = _match_data_point(data_points, target_date)
        if matched is None:
            continue
        values[series_name] = matched

    if not values:
        return None
    if len(values) == 1:
        return next(iter(values.values()))
    return values


def _match_data_point(data_points: list[Any], target_date: date) -> Any:
    for point in data_points:
        if isinstance(point, dict):
            point_date = _coerce_to_date(
                point.get("timestamp") or point.get("date") or point.get("time") or point.get("x")
            )
            if point_date != target_date:
                continue
            payload = {
                key: value
                for key, value in point.items()
                if key not in {"timestamp", "date", "time", "x"} and value is not None
            }
            if not payload:
                return point
            if list(payload.keys()) == ["value"]:
                return payload["value"]
            return payload
    return None


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


__all__ = [
    "ADVANCED_INDICATOR_NAMES",
    "AssetNotFoundError",
    "FormulaExecutionError",
    "IndicatorResultError",
    "JVMStartupError",
    "LibformulaError",
    "compute_advanced_indicators",
]
