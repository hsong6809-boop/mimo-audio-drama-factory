"""配置加载与管理"""

import os
from pathlib import Path
from typing import Any

import yaml


_config_cache: dict | None = None

# 项目根目录（从本文件位置推算）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"


def load_config(config_path: str | Path | None = None) -> dict:
    """加载 YAML 配置文件，支持环境变量覆盖"""
    global _config_cache

    if _config_cache is not None and config_path is None:
        return _config_cache

    if config_path is None:
        config_path = CONFIG_DIR / "default.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 环境变量覆盖（格式：MIMO_PROJECT_OUTPUT_DIR → project.output_dir）
    env_prefix = "MIMO_"
    for key, val in os.environ.items():
        if key.startswith(env_prefix):
            parts = key[len(env_prefix):].lower().split("_")
            _set_nested(config, parts, val)

    _config_cache = config
    return config


def get(section: str, key: str | None = None, default: Any = None) -> Any:
    """快捷获取配置值"""
    config = load_config()
    val = config.get(section, {})
    if key is not None:
        if isinstance(val, dict):
            return val.get(key, default)
        return default
    return val


def _set_nested(d: dict, keys: list[str], value: str):
    """递归设置嵌套字典值"""
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    # 尝试类型转换
    if value.lower() in ("true", "false"):
        value = value.lower() == "true"
    else:
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass
    d[keys[-1]] = value
