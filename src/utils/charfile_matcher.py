#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
字符文件匹配工具：将 OCR 图号标准化后，对比字符文件名（或索引）以找到最佳匹配。
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .config import get_char_root, get_char_index_path, get_match_threshold


_DOTS_RE = re.compile(r"[·•。．∙]")


def normalize_code(s: str) -> str:
    """统一大小写/分隔符/空白，清理连续点号。"""
    s = (s or '').strip().upper().replace(' ', '')
    s = _DOTS_RE.sub('.', s)
    s = re.sub(r"\.+", ".", s)
    return s


def fix_segments(code: str) -> str:
    """按 MAIN 规范做常见易错替换，仅用于匹配，不改变原始展示。"""
    code = normalize_code(code)
    segs = code.split('.')
    if len(segs) != 5:
        return code
    # 位置：AAA.1234.A.123.123
    map_num = str.maketrans({'O': '0', 'I': '1', 'L': '1', 'B': '8', 'S': '5', 'Z': '2', 'G': '6'})
    map_chr = str.maketrans({'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B', '6': 'G'})
    segs[1] = segs[1].translate(map_num)
    segs[2] = segs[2].translate(map_chr)
    segs[3] = segs[3].translate(map_num)
    segs[4] = segs[4].translate(map_num)
    return '.'.join(segs)


def _iter_charfiles(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    for p in root.rglob('*'):
        if p.is_file():
            yield p


def _base_name_pairs(p: Path) -> List[str]:
    """返回用于索引/匹配的两个候选基名：
    - 完整文件名（包含最后一段，如 '... .971'）
    - 去掉最后扩展名的基名（如有扩展名）

    这样可同时兼容“把 .971 当作名字一部分”和“把 .971 当作扩展名”的两种情况。
    """
    name = p.name
    stem = p.stem if p.suffix else p.name
    # 去重并保持顺序
    out: List[str] = []
    for s in (name, stem):
        if s and s not in out:
            out.append(s)
    return out


def build_index(root_dir: Optional[str] = None) -> Dict[str, str]:
    """扫描 root_dir 生成索引：标准化后的文件名（含/不含扩展） → 绝对路径。"""
    root = Path(root_dir or get_char_root()).resolve()
    mapping: Dict[str, str] = {}
    for f in _iter_charfiles(root):
        for base in _base_name_pairs(f):
            norm = normalize_code(base)
            # 同名冲突时保留第一次出现的
            mapping.setdefault(norm, str(f.resolve()))
    return mapping


def save_index(mapping: Dict[str, str], path: Optional[Path] = None, root_dir: Optional[str] = None) -> None:
    out = path or get_char_index_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'root': str(Path(root_dir or get_char_root()).resolve()),
        'count': len(mapping),
        'items': [{'norm': k, 'path': v} for k, v in mapping.items()],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def load_index(path: Optional[Path] = None) -> Optional[Dict[str, str]]:
    fp = path or get_char_index_path()
    if not fp.exists():
        return None
    try:
        obj = json.loads(fp.read_text(encoding='utf-8'))
        items = obj.get('items', [])
        return {it['norm']: it['path'] for it in items if 'norm' in it and 'path' in it}
    except Exception:
        return None


def find_best_charfile(main_code: str, *, use_index: bool = True, allow_scan: bool = True,
                       fuzzy_threshold: Optional[float] = None) -> Tuple[Optional[Path], float]:
    """根据 OCR 的图号查找最佳字符文件。

    返回： (文件路径, 相似度[0-1])；若未命中，路径为 None。
    """
    if not main_code:
        return None, 0.0
    target = fix_segments(main_code)
    threshold = get_match_threshold() if fuzzy_threshold is None else fuzzy_threshold

    candidates: List[Tuple[Path, str]] = []
    if use_index:
        idx = load_index()
        if idx:
            for norm, path in idx.items():
                candidates.append((Path(path), norm))
    if not candidates and allow_scan:
        root = Path(get_char_root())
        for f in _iter_charfiles(root):
            candidates.append((f, normalize_code(_base_name_for_index(f))))

    # 精确匹配
    for path, norm in candidates:
        if norm == target:
            return path, 1.0

    # 模糊匹配
    best_path: Optional[Path] = None
    best_score: float = 0.0
    for path, norm in candidates:
        score = difflib.SequenceMatcher(None, target, norm).ratio()
        if score > best_score:
            best_path, best_score = path, score
    if best_score >= threshold:
        return best_path, best_score
    return None, 0.0
