#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick probe to verify WM_HSCROLL delivery to the vendor grid.

Usage (from repository root):
  env\python.exe tools\probe_hscroll.py --title ".*(VJ-RT1|WH-VJ1000).*"

It prints the target hwnd/class and scroll positions before/after.
"""

import argparse
import time

from pywinauto import Application, Desktop, mouse
from pywinauto.findwindows import find_elements

try:
    import win32gui
    import win32con
    import win32api
except Exception:  # pragma: no cover
    win32gui = None
    win32con = None
    win32api = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--title', default=r'.*(VJ-RT1|WH-VJ1000).*')
    args = ap.parse_args()

    if not (win32gui and win32con and win32api):
        print('pywin32 not available in this environment')
        return 2

    # 可能存在多个同名顶层窗口（例如多个项目/实例同时存在）
    desktop = Desktop(backend='win32')
    wins = desktop.windows(title_re=args.title)
    if not wins:
        print(f'No top-level window matched title: {args.title}')
        return 2
    # 选择策略：优先包含 VSFlexGrid 后代的窗口；否则前台窗口；否则第一个
    def _has_grid(w):
        try:
            w.child_window(class_name='VSFlexGridL').wait('exists', timeout=1)
            return True
        except Exception:
            try:
                w.child_window(class_name_re='VSFlexGrid.*').wait('exists', timeout=1)
                return True
            except Exception:
                return False
    chosen = None
    grids = []
    for w in wins:
        if _has_grid(w):
            chosen = w
            break
    if chosen is None:
        # 尝试使用前台窗口
        try:
            fg = win32gui.GetForegroundWindow() if win32gui else None
            for w in wins:
                if getattr(w, 'handle', None) == fg:
                    chosen = w
                    break
        except Exception:
            pass
    if chosen is None:
        chosen = wins[0]
    win = chosen
    try:
        win.wait('ready', timeout=10)
    except Exception:
        pass
    try:
        win32gui.SetForegroundWindow(win.handle)
    except Exception:
        pass

    # Find grid hwnd via deep enumeration (class-based)
    parent_hwnd = getattr(win, 'handle', None)

    def enum_descendants(root_hwnd):
        seen = set()
        out = []
        stack = [root_hwnd]
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

    hwnd = None
    all_children = enum_descendants(parent_hwnd)
    # Preferred exact class names
    preferred = ['VSFlexGridL', 'VSFlexGrid', 'VSFlexGridWndClass', 'MSFlexGrid']
    for h in all_children:
        try:
            cls = win32gui.GetClassName(h)
        except Exception:
            continue
        if cls in preferred:
            hwnd = h
            break
    # Fallback: fuzzy by class substring
    if hwnd is None:
        for h in all_children:
            try:
                cls = win32gui.GetClassName(h).lower()
            except Exception:
                continue
            if any(k in cls for k in ['flex', 'grid']):
                hwnd = h
                break
    if hwnd is None:
        # List top candidates for manual inspection
        print('No VSFlexGrid* child found. Top candidates (class contains flex/grid/scroll):')
        printed = 0
        for h in all_children:
            try:
                cls = win32gui.GetClassName(h)
            except Exception:
                continue
            low = cls.lower()
            if any(k in low for k in ['flex', 'grid', 'scroll']):
                try:
                    txt = win32gui.GetWindowText(h)
                except Exception:
                    txt = ''
                print('  - hwnd=', hex(h), 'class=', cls, 'text=', txt)
                printed += 1
                if printed >= 20:
                    break
        return 2

    klass = win32gui.GetClassName(hwnd)
    print('Grid hwnd:', hex(hwnd), 'class:', klass)

    def get_pos():
        try:
            si = win32gui.GetScrollInfo(hwnd, win32con.SB_HORZ)
            return {'pos': si.get('pos'), 'min': si.get('min'), 'max': si.get('max'), 'page': si.get('page')}
        except Exception:
            try:
                return {'pos': win32gui.GetScrollPos(hwnd, win32con.SB_HORZ)}
            except Exception:
                return None

    # Focus grid by clicking a safe offset
    # Click safe offset to focus
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    px, py = l + 12, t + 12
    try:
        mouse.click(button='left', coords=(px, py))
    except Exception:
        pass
    time.sleep(0.05)

    before = get_pos()
    print('Before:', before)
    # Left
    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_LEFT, 0)
    time.sleep(0.05)
    # Absolute 90%
    target = int(0.90 * 65535)
    wparam = win32api.MAKELONG(win32con.SB_THUMBPOSITION, target)
    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, wparam, 0)
    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
    time.sleep(0.1)
    after_pos = get_pos()
    print('After-pos:', after_pos)
    # Try THUMBTRACK
    wparam = win32api.MAKELONG(win32con.SB_THUMBTRACK, target)
    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, wparam, 0)
    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
    time.sleep(0.1)
    after_track = get_pos()
    print('After-track:', after_track)

    # PageRight fallback
    steps = 10
    for _ in range(steps):
        win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_PAGERIGHT, 0)
    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
    time.sleep(0.05)
    print('After-pageright: (pos may be None)')

    # LineRight fallback
    steps = 80
    for _ in range(steps):
        win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_LINERIGHT, 0)
    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
    time.sleep(0.05)
    print('After-lineright: (pos may be None)')

    # KEY method fallback (HOME then multiple RIGHT keys directly to hwnd)
    try:
        win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_HOME, 0)
        win32gui.SendMessage(hwnd, win32con.WM_KEYUP, win32con.VK_HOME, 0)
        for _ in range(100):
            win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_RIGHT, 0)
            win32gui.SendMessage(hwnd, win32con.WM_KEYUP, win32con.VK_RIGHT, 0)
        print('After-keys: sent HOME + 100*RIGHT to grid hwnd')
    except Exception as e:
        print('Keys fallback failed:', e)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
