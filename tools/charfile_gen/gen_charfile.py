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
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont


TARGET_HEIGHT = 16
DEFAULT_LINE1 = "09X07/16/100/5"
DEFAULT_LINE2 = "XXXXXX/XXXXXX/XXXXXX/XXXXXX"


@dataclass(frozen=True)
class GenerateResult:
    out_path: Path
    preview_path: Path
    columns: int


def _blank_cols(n: int) -> List[str]:
    if n <= 0:
        return []
    return ["0" * TARGET_HEIGHT for _ in range(n)]


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
    out_h = TARGET_HEIGHT
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
        bits = "".join("1" if bool(mask2[y, x]) else "0" for y in range(TARGET_HEIGHT))
        cols.append(bits)
    return cols


def _compose_columns(
    cn_text: str,
    code_text: str,
    *,
    font: ImageFont.FreeTypeFont,
    gap_cn_to_code: int,
    gap_code: int,
    gap_dot: int,
    gap_cn_inner: int,
    threshold: int,
) -> List[str]:
    cols: List[str] = []

    if cn_text:
        for i, ch in enumerate(cn_text):
            g = _render_glyph_to_columns(ch, font=font, threshold=threshold)
            cols.extend(g)
            if i < len(cn_text) - 1:
                cols.extend(_blank_cols(gap_cn_inner))

    if cn_text and code_text:
        cols.extend(_blank_cols(gap_cn_to_code))

    if code_text:
        for i, ch in enumerate(code_text):
            g = _render_glyph_to_columns(ch, font=font, threshold=threshold)
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
            arr[y, x] = 255 if bit == "1" else 0
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
    ap.add_argument("--font", default=None, help="Optional font file path (.ttf/.ttc).")
    ap.add_argument("--font-size", type=int, default=64, help="Raster font size before normalize-to-16.")
    ap.add_argument("--threshold", type=int, default=180, help="Binarization threshold [0..255].")
    ap.add_argument("--line1", default=DEFAULT_LINE1, help="Header line 1.")
    ap.add_argument("--line2", default=DEFAULT_LINE2, help="Header line 2.")
    ap.add_argument("--gap-cn-code", type=int, default=9, help="Gap between Chinese and code.")
    ap.add_argument("--gap-code", type=int, default=2, help="Gap between code chars (non-dot boundary).")
    ap.add_argument("--gap-dot", type=int, default=3, help="Gap when either side is dot '.'.")
    ap.add_argument("--gap-cn-inner", type=int, default=0, help="Gap between adjacent Chinese chars.")
    ap.add_argument("--preview", default=None, help="Optional preview image path (png/bmp).")
    return ap


def generate_charfile(
    *,
    cn: str,
    code: str,
    out_dir: str = "chars/generated",
    output: Optional[str] = None,
    font: Optional[str] = None,
    font_size: int = 64,
    threshold: int = 180,
    line1: str = DEFAULT_LINE1,
    line2: str = DEFAULT_LINE2,
    gap_cn_code: int = 9,
    gap_code: int = 2,
    gap_dot: int = 3,
    gap_cn_inner: int = 0,
    preview: Optional[str] = None,
) -> GenerateResult:
    if threshold < 0 or threshold > 255:
        raise ValueError("threshold must be in [0,255]")
    if font_size <= 0:
        raise ValueError("font_size must be > 0")

    code_norm = _normalize_code_for_filename(code)
    cn_text = (cn or "").strip()

    font_obj = _load_font(font, int(font_size))
    cols = _compose_columns(
        cn_text,
        code_norm,
        font=font_obj,
        gap_cn_to_code=max(0, int(gap_cn_code)),
        gap_code=max(0, int(gap_code)),
        gap_dot=max(0, int(gap_dot)),
        gap_cn_inner=max(0, int(gap_cn_inner)),
        threshold=int(threshold),
    )
    if not cols:
        raise RuntimeError("Generated 0 columns. Check inputs/font/threshold.")

    if output:
        out_path = Path(output)
    else:
        out_path = Path(out_dir) / code_norm

    _save_charfile(out_path, line1, line2, cols)

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
        font=args.font,
        font_size=args.font_size,
        threshold=args.threshold,
        line1=args.line1,
        line2=args.line2,
        gap_cn_code=args.gap_cn_code,
        gap_code=args.gap_code,
        gap_dot=args.gap_dot,
        gap_cn_inner=args.gap_cn_inner,
        preview=args.preview,
    )

    print(f"[ok] output: {result.out_path}")
    print(f"[ok] columns: {result.columns}")
    print(f"[ok] header1: {args.line1}")
    print(f"[ok] header2: {args.line2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
