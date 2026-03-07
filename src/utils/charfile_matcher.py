#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
字符文件匹配工具：
- 离线构建索引（可选）
- 在线匹配时先精确匹配，再做候选召回 + 加权重排
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Optional, Set, Tuple
from collections import defaultdict

from .config import get_char_root, get_char_index_path, get_match_threshold


_DOTS_RE = re.compile(r"[·•。．∙]")
_SPACES_RE = re.compile(r"\s+")
_SEPARATORS_RE = re.compile(r"[-_/]+")

_NUM_TRANSLATION = str.maketrans({
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1", "|": "1",
    "Z": "2",
    "S": "5",
    "G": "6",
    "B": "8",
})
_ALPHA_TRANSLATION = str.maketrans({
    "0": "O",
    "1": "I",
    "2": "Z",
    "5": "S",
    "6": "G",
    "8": "B",
})

_RUNTIME_CACHE_KEY: Optional[Tuple[str, bool, bool, float]] = None
_RUNTIME_CACHE_VALUE: Optional["RuntimeIndex"] = None


def clear_runtime_cache() -> None:
    global _RUNTIME_CACHE_KEY, _RUNTIME_CACHE_VALUE
    _RUNTIME_CACHE_KEY = None
    _RUNTIME_CACHE_VALUE = None


def _safe_resolve(path_like: Optional[str]) -> Path:
    p = Path(path_like or "")
    try:
        return p.resolve()
    except Exception:
        return p


def normalize_code(s: str) -> str:
    """统一大小写/分隔符/空白，清理连续点号。"""
    s = unicodedata.normalize("NFKC", (s or ""))
    s = _SPACES_RE.sub(".", s).upper()
    s = _SEPARATORS_RE.sub(".", s)
    s = _DOTS_RE.sub('.', s)
    s = re.sub(r"\.+", ".", s)
    s = s.strip(".")
    return s


def fix_segments(code: str) -> str:
    """按 MAIN 规范做常见易错替换，仅用于匹配，不改变原始展示。"""
    code = normalize_code(code)
    segs = code.split('.')
    if len(segs) != 5:
        return code
    # 位置：AAA.1234.A.123.123
    segs[1] = _normalize_numeric_segment(segs[1])
    segs[2] = _normalize_alpha_segment(segs[2])
    segs[3] = _normalize_numeric_segment(segs[3])
    segs[4] = _normalize_numeric_segment(segs[4])
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
    root = _safe_resolve(root_dir or get_char_root())
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
        'root': str(_safe_resolve(root_dir or get_char_root())),
        'count': len(mapping),
        'items': [{'norm': k, 'path': v} for k, v in mapping.items()],
        'version': 2,
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


@dataclass(frozen=True)
class CharfileCandidate:
    path: Path
    norm: str
    segs: Tuple[str, ...]


@dataclass
class RuntimeIndex:
    entries: List[CharfileCandidate]
    exact: Dict[str, Path]
    seg1_map: DefaultDict[str, Set[int]]
    seg12_map: DefaultDict[str, Set[int]]
    trigram_map: DefaultDict[str, Set[int]]
    len_map: DefaultDict[int, Set[int]]


def _normalize_numeric_segment(seg: str) -> str:
    return (seg or "").translate(_NUM_TRANSLATION)


def _normalize_alpha_segment(seg: str) -> str:
    return (seg or "").translate(_ALPHA_TRANSLATION)


def _target_variants(main_code: str) -> List[str]:
    base = normalize_code(main_code)
    if not base:
        return []
    fixed = fix_segments(base)
    variants: List[str] = []
    for v in (base, fixed):
        if v and v not in variants:
            variants.append(v)
    return variants


def _split_segs(norm: str) -> Tuple[str, ...]:
    if not norm:
        return tuple()
    return tuple(norm.split("."))


def _trigrams(s: str) -> Set[str]:
    if not s:
        return set()
    if len(s) <= 3:
        return {s}
    out: Set[str] = set()
    for i in range(len(s) - 2):
        out.add(s[i:i + 3])
    return out


def _score_segment(target: str, cand: str, idx: int) -> float:
    if idx in (1, 3, 4):
        t = _normalize_numeric_segment(target)
        c = _normalize_numeric_segment(cand)
    elif idx == 2:
        t = _normalize_alpha_segment(target)
        c = _normalize_alpha_segment(cand)
    else:
        t = target
        c = cand
    return difflib.SequenceMatcher(None, t, c).ratio()


def _weighted_score(target_norm: str, cand: CharfileCandidate) -> float:
    base_ratio = difflib.SequenceMatcher(None, target_norm, cand.norm).ratio()
    target_segs = _split_segs(target_norm)
    cand_segs = cand.segs

    max_len = max(len(target_segs), len(cand_segs), 1)
    seg_score_sum = 0.0
    for i in range(max_len):
        t = target_segs[i] if i < len(target_segs) else ""
        c = cand_segs[i] if i < len(cand_segs) else ""
        if not t and not c:
            s = 1.0
        elif not t or not c:
            s = 0.0
        else:
            s = _score_segment(t, c, i)
        seg_score_sum += s
    seg_ratio = seg_score_sum / max_len

    t3 = _trigrams(target_norm)
    c3 = _trigrams(cand.norm)
    if not t3 and not c3:
        tri_ratio = 1.0
    else:
        tri_ratio = len(t3 & c3) / max(len(t3 | c3), 1)

    first_seg_bonus = 0.0
    if target_segs and cand_segs and target_segs[0] == cand_segs[0]:
        first_seg_bonus = 0.05

    score = 0.58 * base_ratio + 0.32 * seg_ratio + 0.10 * tri_ratio + first_seg_bonus
    return min(score, 1.0)


def _build_runtime_index_from_mapping(mapping: Dict[str, str]) -> RuntimeIndex:
    entries: List[CharfileCandidate] = []
    exact: Dict[str, Path] = {}
    seg1_map: DefaultDict[str, Set[int]] = defaultdict(set)
    seg12_map: DefaultDict[str, Set[int]] = defaultdict(set)
    trigram_map: DefaultDict[str, Set[int]] = defaultdict(set)
    len_map: DefaultDict[int, Set[int]] = defaultdict(set)

    for norm, path_s in mapping.items():
        norm2 = normalize_code(norm)
        if not norm2:
            continue
        path = Path(path_s)
        candidate = CharfileCandidate(path=path, norm=norm2, segs=_split_segs(norm2))
        idx = len(entries)
        entries.append(candidate)
        exact.setdefault(norm2, path)

        if candidate.segs:
            seg1_map[candidate.segs[0]].add(idx)
            if len(candidate.segs) > 1:
                seg12_map[f"{candidate.segs[0]}.{candidate.segs[1]}"].add(idx)
        for tri in _trigrams(candidate.norm):
            trigram_map[tri].add(idx)
        len_map[len(candidate.norm)].add(idx)

    return RuntimeIndex(
        entries=entries,
        exact=exact,
        seg1_map=seg1_map,
        seg12_map=seg12_map,
        trigram_map=trigram_map,
        len_map=len_map,
    )


def _load_index_payload(path: Optional[Path] = None) -> Optional[dict]:
    fp = path or get_char_index_path()
    if not fp.exists():
        return None
    try:
        obj = json.loads(fp.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return None
        return obj
    except Exception:
        return None


def _load_mapping_from_index(path: Optional[Path] = None) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    payload = _load_index_payload(path)
    if not payload:
        return None, None
    items = payload.get("items", [])
    if not isinstance(items, list):
        return None, None
    mapping: Dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        norm = item.get("norm")
        p = item.get("path")
        if not norm or not p:
            continue
        mapping.setdefault(str(norm), str(p))
    root = payload.get("root")
    return mapping, str(root) if root else None


def _build_mapping_by_scan(root: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for f in _iter_charfiles(root):
        for base in _base_name_pairs(f):
            norm = normalize_code(base)
            if norm:
                mapping.setdefault(norm, str(f.resolve()))
    return mapping


def _load_runtime_index(use_index: bool, allow_scan: bool) -> RuntimeIndex:
    global _RUNTIME_CACHE_KEY, _RUNTIME_CACHE_VALUE
    root = _safe_resolve(get_char_root())
    key = (str(root), bool(use_index), bool(allow_scan), float(get_match_threshold()))
    if _RUNTIME_CACHE_KEY == key and _RUNTIME_CACHE_VALUE is not None:
        return _RUNTIME_CACHE_VALUE

    mapping: Optional[Dict[str, str]] = None
    if use_index:
        idx_mapping, idx_root = _load_mapping_from_index()
        if idx_mapping:
            # 仅当索引 root 与当前配置 root 相同，才认为可直接使用
            if idx_root and _safe_resolve(idx_root) == root:
                mapping = idx_mapping

    if mapping is None and allow_scan:
        mapping = _build_mapping_by_scan(root)

    if mapping is None:
        mapping = {}

    runtime = _build_runtime_index_from_mapping(mapping)
    _RUNTIME_CACHE_KEY = key
    _RUNTIME_CACHE_VALUE = runtime
    return runtime


def _recall_candidate_indexes(runtime: RuntimeIndex, target_norm: str, cap: int = 260) -> Set[int]:
    if not runtime.entries:
        return set()

    target_segs = _split_segs(target_norm)
    chosen: Set[int] = set()

    if target_segs:
        chosen.update(runtime.seg1_map.get(target_segs[0], set()))
        if len(target_segs) > 1:
            key = f"{target_segs[0]}.{target_segs[1]}"
            chosen.update(runtime.seg12_map.get(key, set()))

    overlaps: DefaultDict[int, int] = defaultdict(int)
    for tri in _trigrams(target_norm):
        for idx in runtime.trigram_map.get(tri, set()):
            overlaps[idx] += 1
    if overlaps:
        ranked = sorted(overlaps.items(), key=lambda kv: (-kv[1], runtime.entries[kv[0]].norm))
        for idx, _ in ranked[:cap]:
            chosen.add(idx)

    if len(chosen) < 60:
        length = len(target_norm)
        for delta in (0, 1, -1, 2, -2, 3, -3):
            bucket = runtime.len_map.get(length + delta, set())
            for idx in bucket:
                chosen.add(idx)
                if len(chosen) >= cap:
                    break
            if len(chosen) >= cap:
                break

    if not chosen:
        return set(range(len(runtime.entries)))
    return chosen


def find_top_charfiles(main_code: str, *, top_k: int = 3, use_index: bool = True,
                       allow_scan: bool = True) -> List[Tuple[Path, float]]:
    variants = _target_variants(main_code)
    if not variants:
        return []

    runtime = _load_runtime_index(use_index=use_index, allow_scan=allow_scan)
    if not runtime.entries:
        return []

    # 先尝试精确命中（任一变体）
    for v in variants:
        if v in runtime.exact:
            return [(runtime.exact[v], 1.0)]

    candidate_indexes: Set[int] = set()
    for v in variants:
        candidate_indexes.update(_recall_candidate_indexes(runtime, v))

    path_score: Dict[str, float] = {}
    path_obj: Dict[str, Path] = {}
    for idx in candidate_indexes:
        cand = runtime.entries[idx]
        score = 0.0
        for v in variants:
            score = max(score, _weighted_score(v, cand))
        key = str(cand.path).lower()
        if score > path_score.get(key, -1.0):
            path_score[key] = score
            path_obj[key] = cand.path

    scored: List[Tuple[Path, float]] = [(path_obj[k], s) for k, s in path_score.items()]
    scored.sort(key=lambda x: (-x[1], str(x[0]).lower()))
    if top_k <= 0:
        return []
    return scored[:top_k]


def find_best_charfile(main_code: str, *, use_index: bool = True, allow_scan: bool = True,
                       fuzzy_threshold: Optional[float] = None) -> Tuple[Optional[Path], float]:
    """根据 OCR 的图号查找最佳字符文件。

    返回： (文件路径, 相似度[0-1])；若未命中，路径为 None。
    """
    threshold = get_match_threshold() if fuzzy_threshold is None else float(fuzzy_threshold)
    ranked = find_top_charfiles(
        main_code,
        top_k=1,
        use_index=use_index,
        allow_scan=allow_scan,
    )
    if ranked and ranked[0][1] >= threshold:
        return ranked[0]
    return None, 0.0
