#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
扫描字符文件根目录并生成索引文件（data/char_index.json）。

用法：
  - env\python.exe tools\build_char_index.py --root D:\Vendor\App\Chars
  - 或在 data/config.json 配置 {"char_root": "D:\\Vendor\\App\\Chars"} 后，直接运行：
      env\python.exe tools\build_char_index.py
"""

import argparse
import os
import sys
from pathlib import Path


def _ensure_repo_on_path():
    """将包含 src/ 的目录加入 sys.path（从 tools/ 向上查找）。"""
    here = os.path.abspath(os.path.dirname(__file__))
    cur = here
    for _ in range(6):
        if os.path.isdir(os.path.join(cur, 'src')):
            if cur not in sys.path:
                sys.path.insert(0, cur)
            break
        parent = os.path.abspath(os.path.join(cur, os.pardir))
        if parent == cur:
            break
        cur = parent


_ensure_repo_on_path()

from src.utils.charfile_matcher import build_index, save_index
from src.utils.config import get_char_root, get_char_index_path


def main():
    parser = argparse.ArgumentParser(description='Build char file index for matching')
    parser.add_argument('--root', default=None, help='字符文件根目录（可选，不传则读取配置或默认 chars/）')
    parser.add_argument('--output', default=None, help='索引输出文件（可选，默认 data/char_index.json）')
    args = parser.parse_args()

    root = args.root or get_char_root()
    out = Path(args.output) if args.output else get_char_index_path()

    print(f'[index] 扫描根目录: {root}')
    mapping = build_index(root)
    print(f'[index] 文件数: {len(mapping)}')
    save_index(mapping, out, root_dir=root)
    print(f'[index] 写入索引: {out}')


if __name__ == '__main__':
    main()
