#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Probe script: send paging (SB_PAGELEFT/PAGERIGHT) and line (SB_LINELEFT/LINERIGHT)
WM_HSCROLL messages directly to the vendor grid (VSFlexGrid*) to observe effect.

Usage (from repository root):
  env\python.exe tools\probe_paging.py --title-re ".*VJ-RT1.1 Pro.*" --dir right --pages 3 --lines 0

This only works when the target application window is already running.
"""

import argparse
import time
from typing import Optional, List

from pywinauto import Desktop, mouse

try:
    import win32gui
    import win32con
    import win32api
except Exception:
    win32gui = None  # type: ignore
    win32con = None  # type: ignore
    win32api = None  # type: ignore


def enum_children(hwnd: int) -> List[int]:
    out: List[int] = []
    seen: set[int] = set()
    stack = [hwnd]
    while stack:
        ph = stack.pop()
        def _cb(h, lp):
            if h not in seen:
                seen.add(h)
                out.append(h)
                stack.append(h)
            return True
        try:
            win32gui.EnumChildWindows(ph, _cb, None)
        except Exception:
            pass
    return out


def find_grid_hwnd(top_hwnd: int) -> Optional[int]:
    preferred = ['VSFlexGridL', 'VSFlexGrid', 'VSFlexGridWndClass', 'MSFlexGrid']
    all_children = enum_children(top_hwnd)
    for h in all_children:
        try:
            cls = win32gui.GetClassName(h)
        except Exception:
            continue
        if cls in preferred:
            return h
    for h in all_children:
        try:
            cls = win32gui.GetClassName(h).lower()
        except Exception:
            continue
        if any(k in cls for k in ['flex', 'grid']):
            return h
    return None


def get_scroll_pos(hwnd: int) -> Optional[dict]:
    try:
        si = win32gui.GetScrollInfo(hwnd, win32con.SB_HORZ)
        return {
            'pos': si.get('pos'),
            'min': si.get('min'),
            'max': si.get('max'),
            'page': si.get('page'),
        }
    except Exception:
        try:
            return {'pos': win32gui.GetScrollPos(hwnd, win32con.SB_HORZ)}
        except Exception:
            return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--title-re', default=r'.*(VJ-RT1|WH-VJ1000).*', help='Top-level window title regex')
    ap.add_argument('--dir', choices=['right', 'left'], default='right', help='Paging direction')
    ap.add_argument('--pages', type=int, default=1, help='Number of pages to send')
    ap.add_argument('--lines', type=int, default=0, help='Number of line steps after pages')
    ap.add_argument('--sleep', type=float, default=0.05, help='Delay between steps (seconds)')
    args = ap.parse_args()

    if not (win32gui and win32con and win32api):
        print('[probe] pywin32 not available in this environment')
        return 2

    desktop = Desktop(backend='win32')
    wins = desktop.windows(title_re=args.title_re)
    if not wins:
        print('[probe] no window matches title:', args.title_re)
        return 2

    # Prefer a window that contains VSFlexGrid*
    chosen = None
    for w in wins:
        try:
            w.child_window(class_name='VSFlexGridL').wait('exists', timeout=0.5)
            chosen = w
            break
        except Exception:
            try:
                w.child_window(class_name_re='VSFlexGrid.*').wait('exists', timeout=0.5)
                chosen = w
                break
            except Exception:
                continue
    if chosen is None:
        chosen = wins[0]

    top_hwnd = int(getattr(chosen, 'handle', chosen.element_info.handle))
    try:
        win32gui.SetForegroundWindow(top_hwnd)
    except Exception:
        pass

    grid_hwnd = find_grid_hwnd(top_hwnd)
    if not grid_hwnd:
        print('[probe] VSFlexGrid not found under window. Try Spy++ to confirm class name.')
        return 2
    klass = win32gui.GetClassName(grid_hwnd)
    print(f'[probe] grid hwnd={hex(grid_hwnd)} class={klass}')

    # Focus grid by a safe click
    try:
        l, t, r, b = win32gui.GetWindowRect(grid_hwnd)
        mouse.click(button='left', coords=(l+12, t+12))
        time.sleep(0.03)
    except Exception:
        pass

    before = get_scroll_pos(grid_hwnd)
    print('[probe] before:', before)

    # Send pages
    wparam_page = win32con.SB_PAGERIGHT if args.dir == 'right' else win32con.SB_PAGELEFT
    wparam_line = win32con.SB_LINERIGHT if args.dir == 'right' else win32con.SB_LINELEFT
    for _ in range(max(0, int(args.pages))):
        win32gui.SendMessage(grid_hwnd, win32con.WM_HSCROLL, wparam_page, 0)
        time.sleep(max(0.0, float(args.sleep)))
    win32gui.SendMessage(grid_hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
    time.sleep(0.05)

    # Optional lines
    for _ in range(max(0, int(args.lines))):
        win32gui.SendMessage(grid_hwnd, win32con.WM_HSCROLL, wparam_line, 0)
        time.sleep(max(0.0, float(args.sleep)))
    win32gui.SendMessage(grid_hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
    time.sleep(0.05)

    after = get_scroll_pos(grid_hwnd)
    print('[probe] after:', after)
    print('[probe] done')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
