from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from statistics import mean
from typing import List, Optional


@dataclass(frozen=True)
class CharMetrics:
    """字符文件的简化度量信息。

    - top_row: 目标行（0 基，0 表示最上行）。
    - scroll_percent: 横向滚动百分比（0.0~1.0）。
    """

    top_row: int = 0
    scroll_percent: float = 1.0


def _load_columns_from_file(path: str) -> List[str]:
    """读取 971 字符文件，提取仅包含 0/1 且长度为 16 的行，
    每行代表网格中的 1 列（从上到下 16 点）。
    """
    cols: List[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if len(s) == 16 and set(s) <= {"0", "1"}:
                    cols.append(s)
    except Exception:
        # 读取失败则返回空集合，呼应上层兜底逻辑
        return []
    return cols


def _find_tail_and_toprow(cols: List[str]) -> CharMetrics:
    """根据列数据估计插入位置：
    - tail: 最后一次出现非全零的列索引（再向后空 1 列为插入点）
    - top_row: 取靠近 tail 的若干列的“首个 1 的行号”的平均值，保证上下位置相近
    """
    if not cols:
        return CharMetrics(top_row=0, scroll_percent=1.0)

    # 最后一个包含 '1' 的列
    last_idx = -1
    for i in range(len(cols) - 1, -1, -1):
        if "1" in cols[i]:
            last_idx = i
            break

    if last_idx < 0:
        # 全部为空列
        return CharMetrics(top_row=0, scroll_percent=0.0)

    # 取最后若干（例如 8）列，用它们的首个 1 的行号估计垂直对齐
    window_start = max(0, last_idx - 7)
    window = cols[window_start:last_idx + 1]

    def first_one_row(col: str) -> int:
        for r, ch in enumerate(col):
            if ch == "1":
                return r
        return 8  # 空列兜底返回中线

    rows = [first_one_row(c) for c in window if "1" in c]
    avg_row = int(round(mean(rows))) if rows else 8

    # 横向滚动百分比：希望让 (last_idx + 1) 靠右可见，简单按列数比值估计
    total = len(cols)
    desired = min(total, last_idx + 1)  # 在最后一列后空一列处插入
    scroll = 1.0 if total <= 1 else max(0.0, min(1.0, desired / float(total)))

    return CharMetrics(top_row=max(0, min(15, avg_row)), scroll_percent=scroll)


@lru_cache(maxsize=128)
def get_metrics_with_cache(path: Optional[str]) -> CharMetrics:
    """根据 971 文件推断插入位置与滚动比例：
    - 以最后非全零列为尾，空 1 列后插入
    - 以尾部附近列的首个 1 的平均行号作为插入行（与原内容上下接近）
    """
    if not path:
        return CharMetrics()
    cols = _load_columns_from_file(path)
    return _find_tail_and_toprow(cols)


def get_scroll_plan(path: Optional[str], viewport_cols: int = 123, right_margin: int = 2) -> dict:
    """基于 971 文件计算滚动与定位计划（用于网格 KEY 法更精准地右移）。

    返回字典：
      - steps: 从最左开始需要按 RIGHT 的步数（尽量让末尾刚好可见）
      - top_row: 推荐的垂直行（0..15）
      - total: 总列数
      - last_idx: 最后一个含 '1' 的列索引（-1 表示全空）
      - desired: 目标插入列（last_idx+1，经裁剪）
      - percent: desired/total（用于画布滚动等）
    """
    if not path:
        return {
            'steps': 0,
            'top_row': 0,
            'total': 0,
            'last_idx': -1,
            'desired': 0,
            'percent': 0.0,
        }
    cols = _load_columns_from_file(path)
    metrics = _find_tail_and_toprow(cols) if cols else CharMetrics()
    total = len(cols)

    last_idx = -1
    for i in range(total - 1, -1, -1):
        try:
            if "1" in cols[i]:
                last_idx = i
                break
        except Exception:
            continue

    desired = min(total, last_idx + 1) if last_idx >= 0 else 0
    # 视窗 W 列可见，右侧保留若干列作为余量，使尾列尽量落到可视右边缘内
    W = max(1, int(viewport_cols))
    r = max(0, int(right_margin))
    left_pos = max(0, desired - W + r)
    steps = int(left_pos)

    percent = (desired / float(total)) if total > 0 else 0.0
    return {
        'steps': steps,
        'top_row': int(metrics.top_row),
        'total': total,
        'last_idx': last_idx,
        'desired': desired,
        'percent': float(percent),
    }
