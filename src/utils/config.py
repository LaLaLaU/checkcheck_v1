#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简单配置加载工具：优先读取环境变量，其次读取 data/config.json，最后使用默认值。
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def _config_path() -> Path:
    return Path('data') / 'config.json'


def _load_config_file() -> Dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    path = _config_path()
    if path.exists():
        try:
            _CONFIG_CACHE = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            _CONFIG_CACHE = {}
    else:
        _CONFIG_CACHE = {}
    return _CONFIG_CACHE


def _save_config_file(cfg: Dict[str, Any]) -> None:
    global _CONFIG_CACHE
    _CONFIG_CACHE = dict(cfg) if cfg is not None else {}
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(_CONFIG_CACHE, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        # Best-effort: ignore disk write errors to avoid crashing UI flows
        pass


def update_config(values: Dict[str, Any]) -> Dict[str, Any]:
    """Merge and persist config values.

    Returns the updated dict.
    """
    cfg = _load_config_file().copy()
    cfg.update({k: v for k, v in (values or {}).items() if v is not None})
    _save_config_file(cfg)
    return cfg


def get_char_root() -> str:
    # 环境变量优先
    v = os.environ.get('CHECKCHECK_CHAR_ROOT')
    if v:
        return v
    cfg = _load_config_file()
    return cfg.get('char_root', 'chars')


def get_vendor_exe() -> Optional[str]:
    v = os.environ.get('CHECKCHECK_VENDOR_EXE')
    if v:
        return v
    cfg = _load_config_file()
    return cfg.get('vendor_exe')


def get_vendor_title_re() -> str:
    v = os.environ.get('CHECKCHECK_VENDOR_TITLE_RE')
    if v:
        return v
    cfg = _load_config_file()
    return cfg.get('vendor_title_re', r'.*(VJ-RT1|WH-VJ1000).*')


def get_char_index_path() -> Path:
    cfg = _load_config_file()
    p = cfg.get('char_index', str(Path('data') / 'char_index.json'))
    return Path(p)


def get_match_threshold() -> float:
    v = os.environ.get('CHECKCHECK_CHAR_MATCH_THRESHOLD')
    if v:
        try:
            return float(v)
        except Exception:
            pass
    cfg = _load_config_file()
    try:
        return float(cfg.get('char_match_threshold', 0.8))
    except Exception:
        return 0.8
