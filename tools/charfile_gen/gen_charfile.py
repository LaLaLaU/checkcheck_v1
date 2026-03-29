#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate vendor char files from one-line text using 16-dot column bitmaps.

Output format:
  line1: header (default: 09X07/16/100/5)
  line2: header (default: XXXXXX/XXXXXX/XXXXXX/XXXXXX)
  line3...: each line is exactly 16 chars of 0/1, representing one column.
"""

from __future__ import annotations

import argparse
import functools
import gzip
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont


TARGET_HEIGHT = 16
DEFAULT_LINE1 = "09X07/16/100/5"
DEFAULT_LINE2 = "XXXXXX/XXXXXX/XXXXXX/XXXXXX"
WQY_BITMAP_DIR = Path(__file__).resolve().parent / "wqy-bitmapfont"
WQY_BITMAP_REGULAR = WQY_BITMAP_DIR / "wenquanyi_12pt.pcf"
WQY_BITMAP_BOLD = WQY_BITMAP_DIR / "wenquanyi_12ptb.pcf"

PCF_PROPERTIES = 1 << 0
PCF_METRICS = 1 << 2
PCF_BITMAPS = 1 << 3
PCF_BDF_ENCODINGS = 1 << 5

PCF_COMPRESSED_METRICS = 0x00000100
PCF_GLYPH_PAD_MASK = 3 << 0
PCF_BYTE_MASK = 1 << 2
PCF_BIT_MASK = 1 << 3
PCF_SCAN_UNIT_MASK = 3 << 4

# For code letters/digits only: keep middle 9 rows.
# 16 rows total -> top 3 blank, bottom 4 blank.
CODE_ACTIVE_ROW_START = 3   # inclusive, 0-based
CODE_ACTIVE_ROW_END = 11    # inclusive, 0-based
CODE_WIDTH_SCALE = 1.35
CODE_FALLBACK_WIDTH_SCALE = 1.25
CODE_ONE_WIDTH_SCALE = 1.0

# Dot glyph in code text: a 2x2 small block near lower-right area (rows 11~12, 1-based).
DOT_ROWS = (10, 11)  # 0-based rows
DOT_COLS = 2

# Fixed bitmap font for code text: 5x7 uppercase letters/digits.
# This avoids per-glyph vector scaling distortions.
CODE_BITMAP_FONT_5X7 = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00001", "00001", "00001", "00001", "10001", "10001", "01110"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "/": ["00001", "00010", "00100", "01000", "10000", "00000", "00000"],
}


@dataclass(frozen=True)
class GenerateResult:
    out_path: Path
    preview_path: Optional[Path]
    columns: int


def _blank_cols(n: int) -> List[str]:
    if n <= 0:
        return []
    return ["0" * TARGET_HEIGHT for _ in range(n)]


def _default_wqy_bitmap_font_path(use_bold: bool) -> Path:
    path = WQY_BITMAP_BOLD if use_bold else WQY_BITMAP_REGULAR
    if not path.exists():
        raise FileNotFoundError(f"Required bitmap font file not found: {path}")
    return path


def _default_font_candidates() -> Sequence[Path]:
    win = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    return (
        win / "msyh.ttc",
        win / "simhei.ttf",
        win / "simsun.ttc",
        win / "Deng.ttf",
        win / "arial.ttf",
    )


def _load_font(font_path: Optional[str], font_size: int) -> ImageFont.FreeTypeFont:
    tried: List[str] = []
    if font_path:
        p = Path(font_path)
        tried.append(str(p))
        if p.exists():
            return ImageFont.truetype(str(p), font_size)
        raise FileNotFoundError(f"Font file not found: {p}")

    for p in _default_font_candidates():
        tried.append(str(p))
        if p.exists():
            try:
                return ImageFont.truetype(str(p), font_size)
            except Exception:
                continue

    # Last fallback (ASCII-oriented). Chinese glyph quality is not guaranteed.
    try:
        return ImageFont.load_default()
    except Exception as e:
        raise RuntimeError(f"Unable to load any font. Tried: {tried}") from e


def _render_glyph_to_columns(
    ch: str,
    font: ImageFont.FreeTypeFont,
    out_height: int = TARGET_HEIGHT,
    threshold: int = 180,
) -> List[str]:
    # Draw large first, then normalize to 16-dot height.
    canvas = Image.new("L", (256, 256), color=255)
    draw = ImageDraw.Draw(canvas)
    draw.text((16, 16), ch, fill=0, font=font)

    arr = np.array(canvas, dtype=np.uint8)
    mask = arr < threshold
    if not mask.any():
        return []

    ys, xs = np.where(mask)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    cropped = canvas.crop((x0, y0, x1, y1))

    cw, chh = cropped.size
    if cw <= 0 or chh <= 0:
        return []
    out_h = max(1, int(out_height))
    out_w = max(1, int(round(cw * (out_h / float(chh)))))
    resized = cropped.resize((out_w, out_h), resample=Image.Resampling.NEAREST)

    arr2 = np.array(resized, dtype=np.uint8)
    mask2 = arr2 < threshold
    if not mask2.any():
        return []

    # Trim empty side columns after resize.
    used = np.where(mask2.any(axis=0))[0]
    if used.size == 0:
        return []
    mask2 = mask2[:, used.min() : used.max() + 1]

    cols: List[str] = []
    for x in range(mask2.shape[1]):
        bits = "".join("1" if bool(mask2[y, x]) else "0" for y in range(out_h))
        cols.append(bits)
    return cols


def _embed_cols_in_window(cols: Sequence[str], row_start: int, row_end: int) -> List[str]:
    """Embed variable-height columns into TARGET_HEIGHT rows at [row_start..row_end]."""
    rs = max(0, int(row_start))
    re = min(TARGET_HEIGHT - 1, int(row_end))
    win_h = max(1, re - rs + 1)
    out: List[str] = []
    for col in cols:
        h = len(col)
        if h <= 0:
            continue
        if h > win_h:
            # Safety fallback: sample-compress to window height.
            idxs = [int(round(i * (h - 1) / max(win_h - 1, 1))) for i in range(win_h)]
            core = "".join(col[i] for i in idxs)
        elif h < win_h:
            # Center vertically inside the active window.
            pad_top = (win_h - h) // 2
            pad_bottom = win_h - h - pad_top
            core = ("0" * pad_top) + col + ("0" * pad_bottom)
        else:
            core = col
        bits = ["0"] * TARGET_HEIGHT
        for i, b in enumerate(core):
            bits[rs + i] = "1" if b == "1" else "0"
        out.append("".join(bits))
    return out


def _dot_small_block_cols() -> List[str]:
    cols: List[str] = []
    for _ in range(DOT_COLS):
        bits = ["0"] * TARGET_HEIGHT
        for r in DOT_ROWS:
            if 0 <= r < TARGET_HEIGHT:
                bits[r] = "1"
        cols.append("".join(bits))
    return cols


def _bitmap_rows_to_cols(rows: Sequence[str]) -> List[str]:
    if not rows:
        return []
    h = len(rows)
    w = len(rows[0])
    cols: List[str] = []
    for x in range(w):
        bits = []
        for y in range(h):
            row = rows[y]
            bits.append("1" if x < len(row) and row[x] == "1" else "0")
        cols.append("".join(bits))
    return cols


def _pcf_byte_order(fmt: int) -> str:
    return "big" if (fmt & PCF_BYTE_MASK) else "little"


def _pcf_bit_msb_first(fmt: int) -> bool:
    return bool(fmt & PCF_BIT_MASK)


def _pcf_pad_bytes(fmt: int) -> int:
    return 1 << (fmt & PCF_GLYPH_PAD_MASK)


def _pcf_scan_unit_bytes(fmt: int) -> int:
    return 1 << ((fmt & PCF_SCAN_UNIT_MASK) >> 4)


def _read_u16(buf: bytes, pos: int, order: str) -> int:
    return int.from_bytes(buf[pos : pos + 2], order, signed=False)


def _read_i16(buf: bytes, pos: int, order: str) -> int:
    return int.from_bytes(buf[pos : pos + 2], order, signed=True)


def _read_u32(buf: bytes, pos: int, order: str) -> int:
    return int.from_bytes(buf[pos : pos + 4], order, signed=False)


def _decode_pcf_metric_rows(
    glyph_data: bytes,
    width: int,
    ascent: int,
    descent: int,
    bitmap_format: int,
) -> List[str]:
    width = max(0, int(width))
    height = max(0, int(ascent) + int(descent))
    if width <= 0 or height <= 0:
        return []

    row_raw_bytes = (width + 7) // 8
    row_stride = ((row_raw_bytes + _pcf_pad_bytes(bitmap_format) - 1) // _pcf_pad_bytes(bitmap_format)) * _pcf_pad_bytes(bitmap_format)
    bit_msb_first = _pcf_bit_msb_first(bitmap_format)
    scan_unit = _pcf_scan_unit_bytes(bitmap_format)
    byte_big = (_pcf_byte_order(bitmap_format) == "big")

    rows: List[str] = []
    for row_idx in range(height):
        start = row_idx * row_stride
        row_bytes = glyph_data[start : start + row_stride]
        if len(row_bytes) < row_stride:
            break

        normalized = bytearray()
        if scan_unit > 1:
            for unit_start in range(0, len(row_bytes), scan_unit):
                chunk = row_bytes[unit_start : unit_start + scan_unit]
                if len(chunk) < scan_unit:
                    chunk = chunk + (b"\x00" * (scan_unit - len(chunk)))
                normalized.extend(chunk if byte_big else chunk[::-1])
        else:
            normalized.extend(row_bytes)

        bits: List[str] = []
        for b in normalized[:row_raw_bytes]:
            if bit_msb_first:
                bits.extend("1" if (b & (1 << shift)) else "0" for shift in range(7, -1, -1))
            else:
                bits.extend("1" if (b & (1 << shift)) else "0" for shift in range(0, 8))
        rows.append("".join(bits[:width]).ljust(width, "0"))

    return rows


def _load_pcf_bitmap_glyphs(path: Path) -> Dict[str, List[str]]:
    raw = path.read_bytes()
    if path.suffix.lower() == ".gz" or path.name.lower().endswith(".pcf.gz"):
        raw = gzip.decompress(raw)

    if len(raw) < 8 or raw[:4] != b"\x01fcp":
        raise RuntimeError(f"Invalid PCF header: {path}")

    toc_count = _read_u32(raw, 4, "little")
    toc_pos = 8
    tables: Dict[int, Tuple[int, int, int]] = {}
    for _ in range(toc_count):
        typ = _read_u32(raw, toc_pos, "little")
        fmt = _read_u32(raw, toc_pos + 4, "little")
        size = _read_u32(raw, toc_pos + 8, "little")
        offset = _read_u32(raw, toc_pos + 12, "little")
        tables[typ] = (fmt, size, offset)
        toc_pos += 16

    if PCF_METRICS not in tables or PCF_BITMAPS not in tables or PCF_BDF_ENCODINGS not in tables:
        raise RuntimeError(f"PCF missing required tables: {path}")

    metrics_fmt, _, metrics_off = tables[PCF_METRICS]
    metrics_order = _pcf_byte_order(metrics_fmt)
    pos = metrics_off + 4
    metrics: List[Tuple[int, int, int, int, int]] = []
    if metrics_fmt & PCF_COMPRESSED_METRICS:
        count = _read_u16(raw, pos, metrics_order)
        pos += 2
        for _ in range(count):
            left = raw[pos] - 0x80
            right = raw[pos + 1] - 0x80
            char_width = raw[pos + 2] - 0x80
            ascent = raw[pos + 3] - 0x80
            descent = raw[pos + 4] - 0x80
            metrics.append((left, right, char_width, ascent, descent))
            pos += 5
    else:
        count = _read_u32(raw, pos, metrics_order)
        pos += 4
        for _ in range(count):
            left = _read_i16(raw, pos, metrics_order)
            right = _read_i16(raw, pos + 2, metrics_order)
            char_width = _read_i16(raw, pos + 4, metrics_order)
            ascent = _read_i16(raw, pos + 6, metrics_order)
            descent = _read_i16(raw, pos + 8, metrics_order)
            _ = _read_u16(raw, pos + 10, metrics_order)
            metrics.append((left, right, char_width, ascent, descent))
            pos += 12

    bitmaps_fmt, _, bitmaps_off = tables[PCF_BITMAPS]
    bitmaps_order = _pcf_byte_order(bitmaps_fmt)
    pos = bitmaps_off + 4
    glyph_count = _read_u32(raw, pos, bitmaps_order)
    pos += 4
    offsets: List[int] = []
    for _ in range(glyph_count):
        offsets.append(_read_u32(raw, pos, bitmaps_order))
        pos += 4
    bitmap_sizes = [_read_u32(raw, pos + i * 4, bitmaps_order) for i in range(4)]
    pos += 16
    bitmap_data = raw[pos : pos + bitmap_sizes[bitmaps_fmt & PCF_GLYPH_PAD_MASK]]

    enc_fmt, _, enc_off = tables[PCF_BDF_ENCODINGS]
    enc_order = _pcf_byte_order(enc_fmt)
    pos = enc_off + 4
    min_char2 = _read_u16(raw, pos, enc_order)
    max_char2 = _read_u16(raw, pos + 2, enc_order)
    min_byte1 = _read_u16(raw, pos + 4, enc_order)
    max_byte1 = _read_u16(raw, pos + 6, enc_order)
    default_char = _read_u16(raw, pos + 8, enc_order)
    pos += 10
    _ = default_char

    glyphs: Dict[str, List[str]] = {}
    total = (max_char2 - min_char2 + 1) * (max_byte1 - min_byte1 + 1)
    for enc_index in range(total):
        glyph_index = _read_u16(raw, pos + enc_index * 2, enc_order)
        if glyph_index == 0xFFFF or glyph_index >= len(metrics) or glyph_index >= len(offsets):
            continue
        byte1 = min_byte1 + (enc_index // (max_char2 - min_char2 + 1))
        byte2 = min_char2 + (enc_index % (max_char2 - min_char2 + 1))
        codepoint = (byte1 << 8) | byte2
        try:
            ch = chr(codepoint)
        except ValueError:
            continue

        left, right, char_width, ascent, descent = metrics[glyph_index]
        width = max(0, right - left)
        if width <= 0:
            width = max(0, char_width)
        start = offsets[glyph_index]
        end = offsets[glyph_index + 1] if glyph_index + 1 < len(offsets) else len(bitmap_data)
        glyph_rows = _decode_pcf_metric_rows(bitmap_data[start:end], width, ascent, descent, bitmaps_fmt)
        cols = _bitmap_rows_to_cols(glyph_rows)
        if cols:
            glyphs[ch] = cols

    return glyphs


def _parse_hex_bitmap_rows(hex_payload: str) -> Optional[List[str]]:
    s = (hex_payload or "").strip()
    if not s:
        return None
    try:
        int(s, 16)
    except Exception:
        return None
    bit_len = len(s) * 4
    if bit_len <= 0 or bit_len % TARGET_HEIGHT != 0:
        return None
    w = bit_len // TARGET_HEIGHT
    if w <= 0:
        return None
    bits = bin(int(s, 16))[2:].zfill(bit_len)
    rows = [bits[i * w : (i + 1) * w] for i in range(TARGET_HEIGHT)]
    return rows


def _load_hex_bitmap_glyphs(path: Path) -> Dict[str, List[str]]:
    """
    Load bitmap glyphs from .hex text.
    Expected format: <unicode_hex>:<bitmap_hex>
    Example: 4E2D:00001818247E4242...
    """
    glyphs: Dict[str, List[str]] = {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        cp_hex, bmp_hex = line.split(":", 1)
        cp_hex = cp_hex.strip().lstrip("\ufeff")
        bmp_hex = bmp_hex.strip()
        try:
            cp = int(cp_hex, 16)
            ch = chr(cp)
        except Exception:
            continue
        rows = _parse_hex_bitmap_rows(bmp_hex)
        if not rows:
            continue
        cols = _bitmap_rows_to_cols(rows)
        if cols:
            glyphs[ch] = cols
    return glyphs


def _load_bitmap_glyphs(path_str: Optional[str]) -> Dict[str, List[str]]:
    if not path_str:
        return {}
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"Bitmap font file not found: {p}")
    stat = p.stat()
    return _load_bitmap_glyphs_cached(str(p.resolve()), int(stat.st_mtime_ns), int(stat.st_size))


@functools.lru_cache(maxsize=8)
def _load_bitmap_glyphs_cached(path_str: str, _mtime_ns: int, _size: int) -> Dict[str, List[str]]:
    p = Path(path_str)
    name = p.name.lower()
    ext = p.suffix.lower()
    if name.endswith(".pcf.gz") or ext == ".pcf":
        glyphs = _load_pcf_bitmap_glyphs(p)
    elif ext in {".hex", ".txt"}:
        glyphs = _load_hex_bitmap_glyphs(p)
    else:
        raise ValueError("Bitmap font currently supports .hex/.txt/.pcf/.pcf.gz files.")
    if not glyphs:
        raise RuntimeError(f"No usable glyphs found in bitmap font: {p}")
    return glyphs


def preload_wqy_bitmap_fonts() -> None:
    _load_bitmap_glyphs(str(_default_wqy_bitmap_font_path(False)))
    _load_bitmap_glyphs(str(_default_wqy_bitmap_font_path(True)))


def _resize_cols_height(cols: Sequence[str], target_h: int) -> List[str]:
    th = max(1, int(target_h))
    out: List[str] = []
    for col in cols:
        h = len(col)
        if h <= 0:
            continue
        if h == th:
            out.append(col)
            continue
        if th == 1:
            out.append(col[h // 2])
            continue
        idxs = [int(round(i * (h - 1) / float(th - 1))) for i in range(th)]
        out.append("".join(col[i] for i in idxs))
    return out


def _embed_cols_preserve_height(cols: Sequence[str], total_h: int = TARGET_HEIGHT) -> List[str]:
    if not cols:
        return []
    src_h = len(cols[0])
    if src_h <= 0:
        return []
    if src_h > total_h:
        return _resize_cols_height(cols, total_h)
    row_start = max(0, (total_h - src_h) // 2)
    row_end = min(total_h - 1, row_start + src_h - 1)
    return _embed_cols_in_window(cols, row_start, row_end)


def _embed_cols_bottom_aligned(cols: Sequence[str], total_h: int = TARGET_HEIGHT, bottom_margin: int = 0) -> List[str]:
    if not cols:
        return []
    src_h = len(cols[0])
    if src_h <= 0:
        return []
    if src_h > total_h:
        return _resize_cols_height(cols, total_h)
    row_end = max(0, total_h - 1 - max(0, int(bottom_margin)))
    row_start = max(0, row_end - src_h + 1)
    return _embed_cols_in_window(cols, row_start, row_end)


def _visual_code_bottom_margin(bitmap_glyphs: Dict[str, List[str]]) -> int:
    # Match punctuation to the visual bottom of centered alnum glyphs.
    for probe in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        cols = bitmap_glyphs.get(probe)
        if cols:
            src_h = len(cols[0])
            row_start = max(0, (TARGET_HEIGHT - src_h) // 2)
            row_end = min(TARGET_HEIGHT - 1, row_start + src_h - 1)
            return max(0, TARGET_HEIGHT - 1 - row_end)
    return 3


def _bitmap_char_cols(ch: str, bitmap_glyphs: Dict[str, List[str]], center_punctuation: bool = False) -> List[str]:
    cols = bitmap_glyphs.get(ch)
    if not cols:
        raise ValueError(f"Bitmap font missing glyph: {ch}")
    if ch in ".:,;!?-_=+/\\'\"" and not center_punctuation:
        return _embed_cols_bottom_aligned(
            list(cols),
            TARGET_HEIGHT,
            bottom_margin=_visual_code_bottom_margin(bitmap_glyphs),
        )
    return _embed_cols_preserve_height(list(cols), TARGET_HEIGHT)


def _cols_to_array(cols: Sequence[str]) -> np.ndarray:
    if not cols:
        return np.zeros((0, 0), dtype=np.uint8)
    h = len(cols[0])
    w = len(cols)
    arr = np.zeros((h, w), dtype=np.uint8)
    for x, col in enumerate(cols):
        if len(col) != h:
            continue
        for y, b in enumerate(col):
            if b == "1":
                arr[y, x] = 1
    return arr


def _array_to_cols(arr: np.ndarray) -> List[str]:
    if arr.size == 0:
        return []
    h, w = arr.shape
    cols: List[str] = []
    for x in range(w):
        bits = "".join("1" if int(arr[y, x]) else "0" for y in range(h))
        cols.append(bits)
    return cols


def _rescale_cols_keep_aspect(cols: Sequence[str], target_h: int) -> List[str]:
    arr = _cols_to_array(cols)
    if arr.size == 0:
        return []
    h, w = arr.shape
    th = max(1, int(target_h))
    tw = max(1, int(round(w * (th / float(max(h, 1))))))
    # Foreground as black (0), background white (255), then threshold back.
    img = Image.fromarray(np.where(arr > 0, 0, 255).astype(np.uint8), mode="L")
    resized = img.resize((tw, th), resample=Image.Resampling.BILINEAR)
    arr2 = (np.array(resized, dtype=np.uint8) < 220).astype(np.uint8)
    return _array_to_cols(arr2)


def _trim_side_empty_cols(cols: Sequence[str]) -> List[str]:
    arr = _cols_to_array(cols)
    if arr.size == 0:
        return []
    used = np.where(arr.any(axis=0))[0]
    if used.size == 0:
        return []
    return [cols[i] for i in range(int(used.min()), int(used.max()) + 1)]


def _thin_binary_zhang_suen(arr: np.ndarray, max_iter: int = 64) -> np.ndarray:
    """Skeletonize a binary image into 1-pixel-wide strokes."""
    img = (arr > 0).astype(np.uint8)
    h, w = img.shape
    if h < 3 or w < 3:
        return img

    for _ in range(max_iter):
        changed = False

        to_remove: List[Tuple[int, int]] = []
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                if img[y, x] == 0:
                    continue
                p2 = img[y - 1, x]
                p3 = img[y - 1, x + 1]
                p4 = img[y, x + 1]
                p5 = img[y + 1, x + 1]
                p6 = img[y + 1, x]
                p7 = img[y + 1, x - 1]
                p8 = img[y, x - 1]
                p9 = img[y - 1, x - 1]
                neigh = [p2, p3, p4, p5, p6, p7, p8, p9]
                n = int(sum(neigh))
                if n < 2 or n > 6:
                    continue
                s = int(sum((neigh[i] == 0 and neigh[(i + 1) % 8] == 1) for i in range(8)))
                if s != 1:
                    continue
                if p2 * p4 * p6 != 0:
                    continue
                if p4 * p6 * p8 != 0:
                    continue
                to_remove.append((y, x))

        if to_remove:
            changed = True
            for y, x in to_remove:
                img[y, x] = 0

        to_remove = []
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                if img[y, x] == 0:
                    continue
                p2 = img[y - 1, x]
                p3 = img[y - 1, x + 1]
                p4 = img[y, x + 1]
                p5 = img[y + 1, x + 1]
                p6 = img[y + 1, x]
                p7 = img[y + 1, x - 1]
                p8 = img[y, x - 1]
                p9 = img[y - 1, x - 1]
                neigh = [p2, p3, p4, p5, p6, p7, p8, p9]
                n = int(sum(neigh))
                if n < 2 or n > 6:
                    continue
                s = int(sum((neigh[i] == 0 and neigh[(i + 1) % 8] == 1) for i in range(8)))
                if s != 1:
                    continue
                if p2 * p4 * p8 != 0:
                    continue
                if p2 * p6 * p8 != 0:
                    continue
                to_remove.append((y, x))

        if to_remove:
            changed = True
            for y, x in to_remove:
                img[y, x] = 0

        if not changed:
            break

    return img


def _thin_cols_to_single_pixel(cols: Sequence[str]) -> List[str]:
    arr = _cols_to_array(cols)
    if arr.size == 0:
        return list(cols)
    thin = _thin_binary_zhang_suen(arr)
    if thin.sum() == 0:
        return list(cols)
    out = _array_to_cols(thin)
    out = _trim_side_empty_cols(out)
    return out if out else list(cols)


def _render_cn_single_stroke_columns(
    ch: str,
    font: ImageFont.FreeTypeFont,
    threshold: int,
) -> List[str]:
    # High-res first to reduce jagged artifacts after thinning.
    hi_cols = _render_glyph_to_columns(ch, font=font, out_height=64, threshold=threshold)
    if not hi_cols:
        return []
    hi_thin = _thin_cols_to_single_pixel(hi_cols)
    low_cols = _rescale_cols_keep_aspect(hi_thin, TARGET_HEIGHT)
    low_thin = _thin_cols_to_single_pixel(low_cols)
    return _trim_side_empty_cols(low_thin)


def _scale_cols_width(cols: Sequence[str], width_scale: float = CODE_WIDTH_SCALE) -> List[str]:
    """Widen glyph horizontally without bolding."""
    arr = _cols_to_array(cols)
    if arr.size == 0:
        return []
    h, w = arr.shape
    new_w = max(1, int(round(w * float(width_scale))))
    if new_w == w:
        return list(cols)
    idxs = [int(round(i * (w - 1) / float(max(new_w - 1, 1)))) for i in range(new_w)]
    scaled = np.zeros((h, new_w), dtype=np.uint8)
    for i, src in enumerate(idxs):
        scaled[:, i] = arr[:, src]
    return _array_to_cols(scaled)


def _code_bitmap_cols(ch: str) -> Optional[List[str]]:
    rows = CODE_BITMAP_FONT_5X7.get((ch or "").upper())
    if not rows:
        return None
    return _bitmap_rows_to_cols(rows)


def _compose_columns(
    cn_text: str,
    code_text: str,
    *,
    bitmap_glyphs: Dict[str, List[str]],
    center_punctuation: bool,
    gap_cn_to_code: int,
    gap_code: int,
    gap_dot: int,
    gap_cn_inner: int,
) -> List[str]:
    cols: List[str] = []

    if cn_text:
        for i, ch in enumerate(cn_text):
            g = _bitmap_char_cols(ch, bitmap_glyphs, center_punctuation=center_punctuation)
            cols.extend(g)
            if i < len(cn_text) - 1:
                cols.extend(_blank_cols(gap_cn_inner))

    if cn_text and code_text:
        cols.extend(_blank_cols(gap_cn_to_code))

    if code_text:
        for i, ch in enumerate(code_text):
            g = _bitmap_char_cols(ch, bitmap_glyphs, center_punctuation=center_punctuation)
            cols.extend(g)
            if i < len(code_text) - 1:
                nxt = code_text[i + 1]
                gap = gap_dot if (ch == "." or nxt == ".") else gap_code
                cols.extend(_blank_cols(gap))

    return cols


def _normalize_code_for_filename(code: str) -> str:
    s = (code or "").strip().upper().replace(" ", "")
    if not s:
        raise ValueError("Code is empty.")
    if any(c in s for c in '<>:"/\\|?*'):
        raise ValueError(f"Code contains invalid filename chars: {s}")
    return s


def _save_charfile(path: Path, line1: str, line2: str, cols: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = [line1, line2]
    lines.extend(cols)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _save_preview(path: Path, cols: Sequence[str], scale: int = 16) -> None:
    w = max(1, len(cols))
    h = TARGET_HEIGHT
    arr = np.zeros((h, w), dtype=np.uint8)
    for x, col in enumerate(cols):
        if len(col) != TARGET_HEIGHT:
            continue
        for y, bit in enumerate(col):
            # White background + black dots for readability in UI preview.
            arr[y, x] = 0 if bit == "1" else 255
    img = Image.fromarray(arr, mode="L")
    img = img.resize((w * scale, h * scale), resample=Image.Resampling.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Generate vendor charfile from Chinese text + code.")
    ap.add_argument("--cn", default="", help="Chinese (or any prefix text), single line.")
    ap.add_argument("--code", required=True, help="Main code. Output filename defaults to this value.")
    ap.add_argument("--out-dir", default="chars/generated", help="Output directory.")
    ap.add_argument("--output", default=None, help="Optional full output file path. Overrides --out-dir.")
    ap.add_argument("--bold", action="store_true", help="Use wenquanyi_12ptb.pcf instead of wenquanyi_12pt.pcf.")
    ap.add_argument("--center-punctuation", action="store_true", help="Keep punctuation vertically centered instead of baseline-aligned.")
    ap.add_argument("--line1", default=DEFAULT_LINE1, help="Header line 1.")
    ap.add_argument("--line2", default=DEFAULT_LINE2, help="Header line 2.")
    ap.add_argument("--gap-cn-code", type=int, default=9, help="Gap between Chinese and code.")
    ap.add_argument("--gap-code", type=int, default=2, help="Gap between code chars (non-dot boundary).")
    ap.add_argument("--gap-dot", type=int, default=2, help="Gap when either side is dot '.'.")
    ap.add_argument("--gap-cn-inner", type=int, default=1, help="Gap between adjacent Chinese chars.")
    ap.add_argument("--save-preview", action="store_true", help="Generate preview image.")
    ap.add_argument("--preview", default=None, help="Optional preview image path (png/bmp). Implies --save-preview.")
    return ap


def generate_charfile(
    *,
    cn: str,
    code: str,
    out_dir: str = "chars/generated",
    output: Optional[str] = None,
    bold: bool = False,
    center_punctuation: bool = False,
    line1: str = DEFAULT_LINE1,
    line2: str = DEFAULT_LINE2,
    gap_cn_code: int = 9,
    gap_code: int = 2,
    gap_dot: int = 2,
    gap_cn_inner: int = 1,
    save_preview: bool = False,
    preview: Optional[str] = None,
) -> GenerateResult:
    code_norm = _normalize_code_for_filename(code)
    cn_text = (cn or "").strip()

    bitmap_glyphs = _load_bitmap_glyphs(str(_default_wqy_bitmap_font_path(bool(bold))))
    cols = _compose_columns(
        cn_text,
        code_norm,
        bitmap_glyphs=bitmap_glyphs,
        center_punctuation=bool(center_punctuation),
        gap_cn_to_code=max(0, int(gap_cn_code)),
        gap_code=max(0, int(gap_code)),
        gap_dot=max(0, int(gap_dot)),
        gap_cn_inner=max(0, int(gap_cn_inner)),
    )
    if not cols:
        raise RuntimeError("Generated 0 columns. Check inputs/font/threshold.")

    if output:
        out_path = Path(output)
    else:
        out_path = Path(out_dir) / code_norm

    _save_charfile(out_path, line1, line2, cols)

    preview_path: Optional[Path] = None
    if save_preview or preview:
        if preview:
            preview_path = Path(preview)
        else:
            preview_path = out_path.with_suffix(out_path.suffix + ".png")
        _save_preview(preview_path, cols)

    return GenerateResult(
        out_path=out_path,
        preview_path=preview_path,
        columns=len(cols),
    )


def main() -> int:
    ap = build_arg_parser()
    args = ap.parse_args()
    result = generate_charfile(
        cn=args.cn,
        code=args.code,
        out_dir=args.out_dir,
        output=args.output,
        bold=bool(args.bold),
        center_punctuation=bool(args.center_punctuation),
        line1=args.line1,
        line2=args.line2,
        gap_cn_code=args.gap_cn_code,
        gap_code=args.gap_code,
        gap_dot=args.gap_dot,
        gap_cn_inner=args.gap_cn_inner,
        save_preview=bool(args.save_preview or args.preview),
        preview=args.preview,
    )

    print(f"[ok] output: {result.out_path}")
    print(f"[ok] columns: {result.columns}")
    print(f"[ok] header1: {args.line1}")
    print(f"[ok] header2: {args.line2}")
    if result.preview_path is not None:
        print(f"[ok] preview: {result.preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



