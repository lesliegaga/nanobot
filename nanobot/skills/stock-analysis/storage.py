from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import json
import os


def get_base_dir() -> Path:
    """
    返回用于缓存 stock-analysis 结果的根目录。

    优先使用环境变量 STOCK_SKILL_CACHE_DIR，否则默认为
    当前 skill 目录下的 .cache 子目录。
    """
    env_dir = os.environ.get("STOCK_SKILL_CACHE_DIR")
    if env_dir:
        base = Path(env_dir).expanduser()
    else:
        base = Path(__file__).resolve().parent / ".cache"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sanitize_value(value: str) -> str:
    """
    将 key 部分的值清洗为适合作为文件名的片段。
    仅保留常见安全字符，其余替换为下划线。
    """
    safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    return "".join(ch if ch in safe_chars else "_" for ch in value)


def make_path(kind: str, key_parts: Dict[str, Any]) -> Path:
    """
    根据 kind 与关键参数生成一个稳定的 JSON 文件路径。

    文件名示例：
        daily_fullCode-SH600036_start-2025-06-01_count-120.json
    """
    base = get_base_dir()
    parts = []
    for key in sorted(key_parts.keys()):
        val = str(key_parts[key])
        parts.append(f"{key}-{_sanitize_value(val)}")
    name = f"{kind}_{'__'.join(parts)}.json" if parts else f"{kind}.json"
    return base / name


def save_json(kind: str, key_parts: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[str, Path]:
    """
    将 payload 以 JSON 形式写入缓存文件，返回 (ref_id, path)。

    ref_id 仅用于在日志 / 轻量 JSON 中作为引用标识，格式为：
        <kind>:<filename>
    """
    path = make_path(kind, key_parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    ref_id = f"{kind}:{path.name}"
    return ref_id, path


def ref_to_path(ref_id: str) -> Path:
    """
    将 ref_id 解析为本地缓存文件路径。

    ref_id 形如 "<kind>:<filename>"，其中 <filename> 必须是当前
    缓存目录中的文件名。
    """
    try:
        _kind, filename = ref_id.split(":", 1)
    except ValueError as exc:
        raise ValueError(f"无效的 ref_id: {ref_id!r}") from exc
    base = get_base_dir()
    return base / filename


def load_json(ref_id: str) -> Dict[str, Any]:
    """
    从 ref_id 对应的缓存文件中加载 JSON。
    """
    path = ref_to_path(ref_id)
    if not path.is_file():
        raise FileNotFoundError(f"缓存文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"缓存文件内容不是 JSON 对象: {path}")
    return data


__all__ = [
    "get_base_dir",
    "make_path",
    "save_json",
    "ref_to_path",
    "load_json",
]

