from __future__ import annotations

import time
import os
import re
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict

from pywinauto import Application, mouse
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.keyboard import send_keys

from .charfile_parser import get_metrics_with_cache, get_scroll_plan

try:
    import win32gui  # type: ignore
    import win32con  # type: ignore
    import win32api  # type: ignore
except Exception:  # pragma: no cover
    win32gui = None  # type: ignore
    win32con = None  # type: ignore
    win32api = None  # type: ignore


@dataclass
class UIDriverConfig:
    exe_path: Optional[str] = None
    title_re: str = r".*(VJ-RT1|WH-VJ1000).*"
    root_dir: Optional[str] = None
    y_offset: int = 0
    x_margin_px: int = 20
    monitor_timeout_s: float = 3.0
    # Global delay scaling for UI actions; lower is faster.
    sleep_scale: float = 0.85
    # Grid stabilization wait timeout before scroll/click.
    grid_wait_timeout_s: float = 0.7
    # Parent container for monitor text control: 'main' or section key 'info'/'insert'/'realtime'.
    monitor_parent: str = 'main'
    # Monitor control class name, default ThunderRT6TextBox.
    monitor_class_name: str = 'ThunderRT6TextBox'
    monitor_found_index: Optional[int] = None
    # Transmit button index inside target section; use when title matching is unstable. None means disabled.
    transmit_button_index: Optional[int] = None
    # Viewport column count used by scroll planning.
    viewport_cols: Optional[int] = None
    frame_titles: Dict[str, str] = field(default_factory=lambda: {
        'realtime': '实时元素',
        'insert': '插入元素',
        'info': '信息处置',
    })
    # Scroll behavior: whether to scroll to file end.
    scroll_to_file_end: bool = False
    # Fast paging: HOME -> PageRight x P -> RIGHT x R; fallback to RIGHT x N.
    fast_page: bool = True
    # Page-only mode: skip fine-grained per-column adjustment.
    page_only: bool = False
    # Insert click horizontal tuning.
    tail_click_inner_ratio: float = 0.45
    tail_click_extra_left_cols: int = 0
    # Enable absolute positioning via WM_HSCROLL THUMBPOSITION (not supported by all controls).
    use_thumb_position: bool = False
    # Optionally confirm one more time after monitor text updates.
    confirm_transmit_on_update: bool = True


class VendorUIDriver:
    def __init__(self, cfg: UIDriverConfig) -> None:
        self.cfg = cfg
        self.app: Optional[Application] = None
        self.win = None
        self._viewport_cols_default = 123
        try:
            if getattr(self.cfg, 'viewport_cols', None):
                vc = int(getattr(self.cfg, 'viewport_cols'))
                if vc > 0:
                    self._viewport_cols_default = vc
        except Exception:
            pass
        try:
            self._t0 = time.perf_counter()
        except Exception:
            self._t0 = time.time()
        # Cache the latest grid hwnd to avoid repeated deep enumeration.
        self._grid_hwnd_cached: Optional[int] = None
        # Cache transmit-button hwnd to avoid full lookup each run.
        self._tx_btn_cached: Optional[int] = None

    def _ts(self) -> str:
        try:
            return f"{time.perf_counter() - self._t0:.3f}s"
        except Exception:
            return f"{time.time() - self._t0:.3f}s"

    # Unified sleep helper, scaled by cfg.sleep_scale.
    def _sleep(self, seconds: float) -> None:
        try:
            scale = float(getattr(self.cfg, 'sleep_scale', 0.85))
        except Exception:
            scale = 0.85
        dur = max(0.0, seconds * scale)
        # use real sleep; avoid recursion
        time.sleep(dur)

    # --- app/window ---
    def ensure_app(self) -> None:
        print(f"[drv][{self._ts()}] ensure_app: title_re={self.cfg.title_re} exe={self.cfg.exe_path}")
        try:
            self.app = Application(backend="win32").connect(title_re=self.cfg.title_re, timeout=3)
        except Exception:
            if not self.cfg.exe_path:
                raise RuntimeError("exe_path not set, and no running window found")
            self.app = Application(backend="win32").start(self.cfg.exe_path)
            self._sleep(1.0)
        self.win = self.app.window(title_re=self.cfg.title_re)
        self.win.wait("ready", timeout=15)
        try:
            self.win.set_focus()
        except Exception:
            pass
        try:
            handle = getattr(self.win, 'handle', None)
        except Exception:
            handle = None
        print(f"[drv][{self._ts()}] main window handle={hex(handle) if handle else handle}")

    # --- selectors ---
    def _frame(self, key: str):
        title = self.cfg.frame_titles.get(key)
        if not title:
            raise KeyError(f"鏈煡 frame key: {key}")
        try:
            alias_map = {
                # Prefer correct Chinese titles, keep mojibake aliases for compatibility.
                'info': ['信息处置', '信息处理', '信息', '淇℃伅澶勭疆', '淇℃伅澶勭悊', '淇℃伅'],
                'insert': ['插入元素', '插入', '元素', '鎻掑叆鍏冪礌', '鎻掑叆', '鍏冪礌'],
                'realtime': ['实时元素', '实时', '瀹炴椂鍏冪礌', '瀹炴椂'],
            }
            candidates = [title] + [t for t in alias_map.get(key, []) if t != title]
            deduped: List[str] = []
            for t in candidates:
                if t and t not in deduped:
                    deduped.append(t)
            candidates = deduped
            for t in candidates:
                try:
                    spec = self.win.child_window(title=t, class_name='ThunderRT6Frame')
                    if spec.exists(timeout=0.25):
                        return spec
                except Exception:
                    continue
            for t in candidates:
                try:
                    spec = self.win.child_window(title_re=f".*{re.escape(t)}.*", class_name='ThunderRT6Frame')
                    if spec.exists(timeout=0.2):
                        return spec
                except Exception:
                    continue
            # fallback: first ThunderRT6Frame
            spec = self.win.child_window(class_name='ThunderRT6Frame')
            if spec.exists(timeout=0.5):
                return spec
            raise ElementNotFoundError("ThunderRT6Frame not found")
        except ElementNotFoundError as e:
            raise RuntimeError(f"鎵句笉鍒板垎鍖烘鏋? {title} (ThunderRT6Frame)") from e

    def _btn(self, parent, caption: str):
        return parent.child_window(title=caption, class_name='ThunderRT6CommandButton').wait('enabled', timeout=5)

    @staticmethod
    def _norm_ui_text(s: str) -> str:
        text = str(s or "").strip().replace(" ", "").replace("\u3000", "")
        text = text.replace("（", "(").replace("）", ")").replace("&", "")
        text = re.sub(r"\([^)]*\)", "", text)
        return text

    def _click_button_by_titles(self, parent, titles: List[str], *, timeout: float = 0.8) -> bool:
        clean_titles = [str(t) for t in titles if str(t).strip()]
        # Exact title lookup first.
        for cap in clean_titles:
            try:
                parent.child_window(title=cap, class_name='ThunderRT6CommandButton').wait('enabled', timeout=timeout).click_input()
                return True
            except Exception:
                continue

        # Fallback: scan all command buttons and fuzzy-match normalized text.
        norms = [self._norm_ui_text(t) for t in clean_titles if self._norm_ui_text(t)]
        if not norms:
            return False
        try:
            cands = parent.wrapper_object().descendants(class_name='ThunderRT6CommandButton')
        except Exception:
            cands = []
        for b in cands:
            try:
                txt_norm = self._norm_ui_text(b.window_text())
                if any(txt_norm == n or txt_norm.startswith(n) or n in txt_norm for n in norms):
                    b.click_input()
                    return True
            except Exception:
                continue
        return False

    def _textbox_by_index(self, parent, idx: int):
        return parent.child_window(class_name='ThunderRT6TextBox', found_index=idx).wait('exists', timeout=5)

    def _combo_by_index(self, parent, idx: int):
        return parent.child_window(class_name='ThunderRT6ComboBox', found_index=idx).wait('exists', timeout=5)

    def _grid(self, parent, *, fast: bool = False):
        # Prefer cached grid hwnd when still valid.
        if win32gui and self._grid_hwnd_cached:
            try:
                if win32gui.IsWindow(self._grid_hwnd_cached):
                    cls = (win32gui.GetClassName(self._grid_hwnd_cached) or '').lower()
                    if any(k in cls for k in ['flex', 'grid']):
                        return self.app.window(handle=self._grid_hwnd_cached)
            except Exception:
                pass

        # Limit search to the given parent's subtree first for better performance.
        if not (win32gui and getattr(parent, 'wrapper_object', None)):
            # Fallback to pywinauto exists checks with very short timeout.
            try:
                spec = parent.child_window(class_name='VSFlexGridL')
                if spec.exists(timeout=0.2):
                    return spec
            except Exception:
                pass
            try:
                spec = parent.child_window(class_name_re='VSFlexGrid.*')
                if spec.exists(timeout=0.2):
                    return spec
            except Exception:
                pass
            raise ElementNotFoundError('VSFlexGrid not found')

        try:
            ph = None
            try:
                ph = parent.wrapper_object().handle
            except Exception:
                pass
            if not ph:
                # Last fallback: use main window handle.
                ph = getattr(self.win, 'handle', None)
            if not ph:
                raise RuntimeError('no parent handle for grid search')

            preferred = ['VSFlexGridL', 'VSFlexGrid', 'VSFlexGridWndClass', 'MSFlexGrid']
            found: Optional[int] = None

            def enum_children(root):
                out: List[int] = []
                if not win32gui:
                    return out
                seen: set[int] = set()
                stack = [root]
                while stack:
                    nh = stack.pop()
                    def _cb(h, lp):
                        if h not in seen:
                            seen.add(h)
                            out.append(h)
                            stack.append(h)
                        return True
                    try:
                        win32gui.EnumChildWindows(nh, _cb, None)
                    except Exception:
                        pass
                return out

            for h in enum_children(ph):
                try:
                    cls = win32gui.GetClassName(h)
                except Exception:
                    continue
                if cls in preferred:
                    found = h
                    break
            if found is None:
                for h in enum_children(ph):
                    try:
                        low = win32gui.GetClassName(h).lower()
                    except Exception:
                        continue
                    if any(k in low for k in ['vsflexgrid', 'flex', 'grid']):
                        found = h
                        break
            if found:
                self._grid_hwnd_cached = found
                return self.app.window(handle=found)

            # Final fallback: if not found in subtree, scan main window subtree once.
            try:
                root_main = getattr(self.win, 'handle', None)
            except Exception:
                root_main = None
            if root_main and ph and root_main != ph:
                for h in enum_children(root_main):
                    try:
                        cls = win32gui.GetClassName(h)
                    except Exception:
                        continue
                    if cls in preferred:
                        self._grid_hwnd_cached = h
                        return self.app.window(handle=h)
                for h in enum_children(root_main):
                    try:
                        low = win32gui.GetClassName(h).lower()
                    except Exception:
                        continue
                    if any(k in low for k in ['vsflexgrid', 'flex', 'grid']):
                        self._grid_hwnd_cached = h
                        return self.app.window(handle=h)
        except Exception:
            pass
        raise ElementNotFoundError('VSFlexGrid not found')

    # --- file and input ---
    def open_char_file(self, full_path: str) -> None:
        # Trigger the standard Open dialog from the "load info" button.
        try:
            # Ensure main window is foreground first.
            try:
                if win32gui and getattr(self.win, 'handle', None):
                    win32gui.SetForegroundWindow(self.win.handle)  # type: ignore[attr-defined]
            except Exception:
                pass
            self.win.set_focus()

            opened = False
            load_titles = ['载入信息', '导入信息', '杞藉叆淇℃伅']
            # 1) Prefer clicking load button inside info area.
            try:
                frm = self._frame('info')
                opened = self._click_button_by_titles(frm, load_titles, timeout=0.25)
                if opened:
                    print("[drv] open_char_file: clicked load-info button in info frame")
            except Exception:
                opened = False

            # 2) Fallback: scan/load from main window scope.
            if not opened:
                try:
                    opened = self._click_button_by_titles(self.win, load_titles, timeout=0.2)
                    if opened:
                        print("[drv] open_char_file: clicked load-info button in main window")
                except Exception:
                    opened = False

            # Do not use hotkey fallback. If button failed, return directly.
            if not opened:
                print('[drv] open_char_file: open-dialog by button failed; skip hotkey fallback')
                return

            self._sleep(0.03)
        except Exception:
            pass
        try:
            print(f"[drv][{self._ts()}] open_char_file: wait dialog ...")
            def _pick_open_dialog():
                specs = []
                try:
                    for w in self.app.windows(class_name='#32770'):
                        try:
                            wr = w.wrapper_object()
                            if not wr.is_visible() or not wr.is_enabled():
                                continue
                            edits = wr.descendants(class_name='Edit')
                            if not edits:
                                continue
                            h = int(getattr(wr, 'handle', getattr(wr, 'element_info').handle))
                            specs.append((h, self.app.window(handle=h)))
                        except Exception:
                            continue
                except Exception:
                    pass
                if not specs:
                    return None
                fg = None
                try:
                    if win32gui:
                        fg = win32gui.GetForegroundWindow()
                except Exception:
                    fg = None
                if fg:
                    for h, spec in specs:
                        if h == fg:
                            return spec
                specs.sort(key=lambda x: x[0], reverse=True)
                return specs[0][1]

            dlg = None
            deadline = time.time() + 1.0
            while time.time() < deadline:
                cand = _pick_open_dialog()
                if cand is not None:
                    try:
                        cand.wait('ready', timeout=0.2)
                        dlg = cand
                        break
                    except Exception:
                        pass
                self._sleep(0.015)
            if dlg is None:
                dlg = self.app.window(class_name='#32770')
                dlg.wait('exists', timeout=0.4)
                dlg.wait('ready', timeout=0.4)
            try:
                if win32gui and hasattr(dlg, 'handle'):
                    win32gui.SetForegroundWindow(dlg.handle)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                dlg.set_focus()
            except Exception:
                pass

            # Input only in the file-name Edit box to avoid sending keys to dialog root.
            used_edit = None
            target_path = os.path.abspath(full_path)

            def _norm_path_text(s: str) -> str:
                return os.path.normcase(str(s or "").strip().strip('"\t '))

            target_norm = _norm_path_text(target_path)

            # Prefer the bottom-most visible/enabled Edit as "File name".
            try:
                edits = dlg.wrapper_object().descendants(class_name='Edit')
            except Exception:
                edits = []

            ranked_edits = []
            for ed in edits:
                try:
                    if not ed.is_visible() or not ed.is_enabled():
                        continue
                    rc = ed.rectangle()
                    ranked_edits.append((int(rc.top), int(rc.left), ed))
                except Exception:
                    continue
            ranked_edits.sort(key=lambda x: (x[0], x[1]), reverse=True)

            for _top, _left, ed in ranked_edits:
                try:
                    ed.set_focus()
                    try:
                        ed.set_edit_text("")
                    except Exception:
                        pass
                    ed.set_edit_text(target_path)
                    if _norm_path_text(ed.window_text()) == target_norm:
                        used_edit = ed
                        break
                except Exception:
                    continue

            # Fallback to the default Edit if ranking did not match.
            if used_edit is None:
                try:
                    ed = dlg.child_window(class_name='Edit').wait('exists', timeout=0.35).wrapper_object()
                    ed.set_focus()
                    ed.set_edit_text(target_path)
                    if _norm_path_text(ed.window_text()) == target_norm:
                        used_edit = ed
                except Exception:
                    pass

            if used_edit is not None:
                print(f"[drv][{self._ts()}] open_char_file: path filled, confirming OPEN")
                clicked_open = False
                # Fast path: scan visible/enabled buttons once and pick Open by normalized text.
                try:
                    btns = dlg.wrapper_object().descendants(class_name='Button')
                except Exception:
                    btns = []
                for b in btns:
                    try:
                        if not b.is_visible() or not b.is_enabled():
                            continue
                        txt = self._norm_ui_text(b.window_text())
                        if txt in ('打开', 'open') or txt.startswith('打开') or txt.startswith('open'):
                            b.click_input()
                            clicked_open = True
                            break
                    except Exception:
                        continue
                for cap in ('打开(&O)', '打开(O)', '打开', 'Open', '&Open'):
                    if clicked_open:
                        break
                    try:
                        btn = dlg.child_window(title=cap, class_name='Button').wait('enabled', timeout=0.15).wrapper_object()
                        btn.click_input()
                        clicked_open = True
                        break
                    except Exception:
                        continue

                if not clicked_open:
                    try:
                        used_edit.type_keys('{ENTER}')
                    except Exception:
                        try:
                            send_keys('{ENTER}')
                        except Exception:
                            pass

                try:
                    dlg.wait_not('visible', timeout=0.6)
                except Exception:
                    try:
                        send_keys('{ENTER}')
                    except Exception:
                        pass
                    try:
                        dlg.wait_not('visible', timeout=0.3)
                    except Exception:
                        pass
            else:
                print(f"[drv] warn: file dialog filename Edit not found/matched; skip typing")
            self._sleep(0.12)
            # Controls may rebuild after file import; clear cached handles for rediscovery.
            try:
                self._grid_hwnd_cached = None  # type: ignore[attr-defined]
                self._tx_btn_cached = None     # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            # Avoid further key injection into dialog to prevent system beep.
            self._sleep(0.08)

    def fill_sortie(self, value: str) -> None:
        try:
            print(f"[drv][{self._ts()}] fill_sortie: begin value='{value}'")
            frm = self._frame('insert')
            tb = self._textbox_by_index(frm, 0)
            tb.set_edit_text(value)
        except Exception:
            try:
                send_keys(value)
            except Exception:
                pass
        self._sleep(0.06)
        print(f"[drv][{self._ts()}] fill_sortie: end")

    # --- canvas and scrolling ---
    def _get_canvas_rect(self) -> Tuple[int, int, int, int]:
        rect = self.win.rectangle()
        left = rect.left + 100
        top = rect.top + 120
        right = rect.right - 200
        bottom = rect.top + 420
        return left, top, right, bottom

    def _wait_grid_stable(self, timeout: float = 1.0, poll: float = 0.05) -> None:
        try:
            t0 = time.perf_counter()
            print(f"[drv][{self._ts()}] wait_grid_stable: start timeout={timeout:.2f}s")
            deadline = time.time() + max(0.1, float(timeout))
            last = None
            stable = 0
            while time.time() < deadline:
                try:
                    frm = self._frame('info')
                    wr = self._grid(frm, fast=True).wrapper_object()
                    h = int(getattr(wr, 'handle', getattr(wr, 'element_info').handle))
                except Exception:
                    h = None
                if h and h == last:
                    stable += 1
                    if stable >= 3:
                        break
                else:
                    stable = 0
                    last = h
                self._sleep(max(0.02, poll))
        except Exception:
            pass
        finally:
            try:
                elapsed = time.perf_counter() - t0
            except Exception:
                elapsed = 0.0
            print(f"[drv][{self._ts()}] wait_grid_stable: done elapsed={elapsed:.3f}s")

    def _scroll_grid_to_percent(self, grid, percent: float, *, charfile_path: Optional[str] = None) -> None:
        # Focus grid first so keyboard/scroll messages hit the right control.
        try:
            rect = grid.rectangle(); px = rect.left + 12; py = rect.top + 12
            try:
                if win32gui and hasattr(self.win, 'handle'):
                    win32gui.SetForegroundWindow(self.win.handle)
            except Exception:
                pass
            self.win.click_input(coords=(px, py))
            self._sleep(0.03)
            mouse.click(button='right', coords=(px, py))
            self._sleep(0.02)
        except Exception:
            pass

        if not charfile_path:
            return

        try:
            plan = get_scroll_plan(charfile_path, viewport_cols=self._viewport_cols_default, right_margin=2)
            # Refocus and click grid so scroll messages go to the correct control.
            try:
                grid.set_focus()
            except Exception:
                pass
            try:
                rect = grid.rectangle()
                self.win.click_input(coords=(rect.left + 8, rect.top + 8))
                self._sleep(0.01)
            except Exception:
                pass
            hwnd = int(getattr(grid, 'handle', getattr(grid, 'element_info').handle))
            try:
                cls = win32gui.GetClassName(hwnd) if win32gui else '<no-win32gui>'
            except Exception:
                cls = '<unknown>'
            print(f"[drv][{self._ts()}] grid hwnd={hex(hwnd)} class={cls}")

            # Core parameters: desired / S / P / R.
            W = int(self._viewport_cols_default)
            r = 2
            if self.cfg.scroll_to_file_end:
                total = int(plan.get('total', 0))
                desired = max(0, total - 1)
            else:
                desired = int(plan.get('desired', 0))
            desired = max(0, desired)
            S = max(0, desired - W + r)
            try:
                percent = plan.get('percent')
            except Exception:
                percent = None
            print(f"[drv][{self._ts()}] grid-scroll plan: desired={desired} W={W} r={r} steps={S} percent={percent}")

            # Reset to far-left first.
            if not win32gui:
                print("[drv] warn: win32gui not available; WM_HSCROLL disabled by config")
                return

            # Prefer SB_LEFT and fallback to HOME key.
            try:
                win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_LEFT, 0)
                win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
            except Exception:
                try:
                    win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_HOME, 0)
                    win32gui.SendMessage(hwnd, win32con.WM_KEYUP, win32con.VK_HOME, 0)
                except Exception:
                    pass
            self._sleep(0.012)

            # Optional absolute positioning; disabled by default.
            if getattr(self.cfg, 'use_thumb_position', False):
                try:
                    import win32api  # type: ignore
                    pos16 = max(0, min(65535, int(float(plan.get('percent', 0.0)) * 65535)))
                    wparam = win32api.MAKELONG(win32con.SB_THUMBPOSITION, pos16)
                    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, wparam, 0)
                    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
                    print(f"[drv] hscroll: THUMBPOSITION pos16={pos16}")
                except Exception:
                    print("[drv] hscroll: THUMBPOSITION not supported; skipping")

            if self.cfg.fast_page and desired >= W:
                # Split S into page and residual line scroll steps.
                P = max(0, S // W)
                R = max(0, S - P * W)
                if getattr(self.cfg, 'page_only', False):
                    R = 0
                try:
                    for i in range(P):
                        win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_PAGERIGHT, 0)
                        self._sleep(0.01)
                    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
                    self._sleep(0.01)
                except Exception:
                    pass
                # Residual R: continue RIGHT x R.
                try:
                    for i in range(R):
                        win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_LINERIGHT, 0)
                        if (i % 10) == 0:
                            self._sleep(0.003)
                    win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
                except Exception:
                    pass
                print(f"[drv] fast-page: P={P} pages, R={R} rights, S={S}, W={self._viewport_cols_default}")
            else:
                # Fallback to line-by-line RIGHT scroll.
                steps = S
                if steps > 0:
                    try:
                        for i in range(steps):
                            win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_LINERIGHT, 0)
                            if (i % 10) == 0:
                                self._sleep(0.003)
                        win32gui.SendMessage(hwnd, win32con.WM_HSCROLL, win32con.SB_ENDSCROLL, 0)
                    except Exception:
                        pass
                print(f"[drv] grid-scroll KEY plan: steps={steps} plan={plan}")
        except Exception as e:
            print(f"[drv] grid-scroll KEY plan error: {e}")

    def _click_canvas(self, x: int, y: int) -> None:
        try:
            self.win.click_input(coords=(x, y))
        except Exception:
            pass
        self._sleep(0.03)

    def prepare_scroll_for_tail(self, charfile_path: str) -> None:
        try:
            print(f"[drv][{self._ts()}] prepare_scroll_for_tail: begin")
            self._wait_grid_stable(timeout=getattr(self.cfg, 'grid_wait_timeout_s', 0.7))
            frm = self._frame('info')
            # Use non-fast handle resolution for scrolling to ensure viewport target is correct.
            grid = self._grid(frm).wrapper_object()
            plan = get_scroll_plan(charfile_path, viewport_cols=self._viewport_cols_default, right_margin=2)
            percent = float(plan.get('percent', 1.0) or 1.0)
            self._scroll_grid_to_percent(grid, percent, charfile_path=charfile_path)
        except Exception:
            pass

    def insert_text_at_tail(self, charfile_path: str) -> None:
        try:
            print(f"[drv][{self._ts()}] insert_text_at_tail: begin")
            self._wait_grid_stable(timeout=getattr(self.cfg, 'grid_wait_timeout_s', 0.7))
            frm = self._frame('info')
            # Use non-fast handle resolution for scrolling to ensure viewport target is correct.
            grid = self._grid(frm).wrapper_object()
            plan = get_scroll_plan(charfile_path, viewport_cols=self._viewport_cols_default, right_margin=2)
            percent = float(plan.get('percent', 1.0) or 1.0)
            self._scroll_grid_to_percent(grid, percent, charfile_path=charfile_path)
        except Exception:
            pass

        try:
            metrics = get_metrics_with_cache(charfile_path)
            left, top, right, bottom = self._get_canvas_rect()
            canvas_h = max(1, bottom - top)
            cell_h = canvas_h / 16.0
            anchor_y = int(top + (metrics.top_row + self.cfg.y_offset) * cell_h + 1)

            # Horizontal click: place near the visible column of the tail content, slightly left of center.
            try:
                W = int(self._viewport_cols_default)
                r = 2
                # Use same scroll-plan parameters to locate the tail content column.
                plan = get_scroll_plan(charfile_path, viewport_cols=W, right_margin=r)
                last_idx = max(0, int(plan.get('last_idx', 0)))
                desired = max(0, int(plan.get('desired', last_idx + 1)))
                S = max(0, desired - W + r)
                # In page_only mode, effective steps become page steps P*W.
                if getattr(self.cfg, 'page_only', False):
                    P_eff = S // W
                    S_eff = P_eff * W
                else:
                    S_eff = S
                screen_col = max(0, min(W - 1, last_idx - S_eff))
                # Allow extra left offset in columns to click closer to content area.
                extra_left = int(getattr(self.cfg, 'tail_click_extra_left_cols', 0) or 0)
                screen_col = max(0, screen_col - max(0, extra_left))
                # In-column offset ratio: 0.0 (left) to 1.0 (right).
                inner = float(getattr(self.cfg, 'tail_click_inner_ratio', 0.45) or 0.45)
                inner = max(0.1, min(0.9, inner))
                col_w = max(1.0, (right - left) / float(W))
                gx_calc = int(left + (screen_col + inner) * col_w)
                gx = max(left + 5, min(right - 8, gx_calc))
            except Exception:
                gx = max(left + 5, right - max(8, self.cfg.x_margin_px))

            gy = max(top + 5, min(bottom - 8, anchor_y))
            print(f"[drv][{self._ts()}] canvas click at tail: ({gx},{gy})")
            self.win.click_input(coords=(gx, gy))
        except Exception:
            pass
        self._sleep(0.06)

        try:
            ins_frm = self._frame('insert')
            insert_titles = ['插入文字', '插入文本', '鎻掑叆鏂囧瓧']
            try:
                if self._click_button_by_titles(ins_frm, insert_titles, timeout=0.9):
                    print(f"[drv][{self._ts()}] insert: clicked insert-text button")
                else:
                    raise RuntimeError("insert-text button not found")
            except Exception:
                # Scan same-class buttons and match exact title.
                try:
                    cands = ins_frm.wrapper_object().descendants(class_name='ThunderRT6CommandButton')
                except Exception:
                    cands = []
                insert_norms = {self._norm_ui_text(t) for t in insert_titles}
                for b in cands:
                    try:
                        txt = ''
                        try:
                            txt = b.window_text()
                        except Exception:
                            pass
                        if self._norm_ui_text(str(txt)) in insert_norms:
                            b.click_input()
                            print(f"[drv] insert: clicked inferred '{txt}'")
                            break
                    except Exception:
                        continue
        except Exception:
            try:
                send_keys('{ENTER}')
            except Exception:
                pass
        self._sleep(0.12)

    def transmit(self) -> None:
        try:
            print(f"[drv][{self._ts()}] transmit: begin")
            # Focus main window first.
            try:
                self.win.set_focus()
            except Exception:
                pass
            # Prefer cached hwnd if still valid.
            if win32gui and getattr(self, '_tx_btn_cached', None):
                try:
                    if (win32gui.IsWindow(self._tx_btn_cached) and
                        win32gui.GetClassName(self._tx_btn_cached) == 'ThunderRT6CommandButton'):
                        # Capture monitor baseline first, then click.
                        ctrl, baseline = self._capture_monitor_text()
                        self.app.window(handle=self._tx_btn_cached).click_input()
                        print("[drv] transmit: clicked cached transmit button")
                        # Optional: confirm once monitor updates.
                        if getattr(self.cfg, 'confirm_transmit_on_update', False):
                            if self.wait_monitor_updated(self.cfg.monitor_timeout_s, baseline):
                                try:
                                    self.app.window(handle=self._tx_btn_cached).click_input()
                                    print("[drv] transmit: re-clicked after monitor update")
                                except Exception:
                                    pass
                        self._sleep(0.10)
                        return
                except Exception:
                    self._tx_btn_cached = None

            # Capture baseline first, then locate and click transmit precisely.
            ctrl, baseline = self._capture_monitor_text()
            tx_titles = ['传输信息', '发送信息', '浼犺緭淇℃伅']
            btn = None
            for cap in tx_titles:
                try:
                    btn = self._btn(self.win, cap)
                    break
                except Exception:
                    continue
            if btn is None:
                if self._click_button_by_titles(self.win, tx_titles, timeout=1.0):
                    print("[drv] transmit: clicked transmit button by scan")
                    self._sleep(0.10)
                    return
                raise RuntimeError("transmit button not found")
            # Cache hwnd for next direct click.
            try:
                h = int(getattr(btn, 'handle', getattr(btn, 'element_info').handle))
                self._tx_btn_cached = h
            except Exception:
                pass
            btn.click_input()
            print("[drv] transmit: clicked transmit button")
            # Optional: confirm once monitor updates.
            if getattr(self.cfg, 'confirm_transmit_on_update', False):
                if self.wait_monitor_updated(self.cfg.monitor_timeout_s, baseline):
                    try:
                        # If cache is stale, fall back to exact lookup once.
                        if win32gui and getattr(self, '_tx_btn_cached', None) and win32gui.IsWindow(self._tx_btn_cached):
                            self.app.window(handle=self._tx_btn_cached).click_input()
                        else:
                            clicked = self._click_button_by_titles(self.win, tx_titles, timeout=0.8)
                            if not clicked:
                                raise RuntimeError("transmit re-click not found")
                        print("[drv] transmit: re-clicked after monitor update")
                    except Exception:
                        pass
        except Exception as e:
            print(f"[drv] transmit error: {e}")
        self._sleep(0.10)

    def _capture_monitor_text(self) -> Tuple[Optional[object], str]:
        def _resolve_parent() -> Optional[object]:
            parent_key = str(getattr(self.cfg, 'monitor_parent', 'info') or 'info')
            if parent_key == 'main':
                return self.win
            try:
                return self._frame(parent_key)
            except Exception:
                return None

        ctrl = None
        baseline = None
        parent = _resolve_parent()
        cls_name = str(getattr(self.cfg, 'monitor_class_name', 'ThunderRT6TextBox') or 'ThunderRT6TextBox')
        found_idx = getattr(self.cfg, 'monitor_found_index', 0)

        # Prefer locating monitor control under configured parent.
        if parent is not None:
            try:
                if found_idx is not None:
                    ctrl = parent.child_window(class_name=cls_name, found_index=int(found_idx))
                    baseline = ctrl.window_text()
                else:
                    # No fixed index: pick candidate with longest text.
                    wr = parent.wrapper_object()
                    candidates = []
                    try:
                        candidates = wr.descendants(class_name=cls_name)
                    except Exception:
                        candidates = []
                    # Fallback class names: ThunderRT6Label / Static.
                    if not candidates:
                        for alt in ('ThunderRT6Label', 'Static'):
                            try:
                                candidates = wr.descendants(class_name=alt)
                                if candidates:
                                    cls_name = alt
                                    break
                            except Exception:
                                continue
                    # 閫夋嫨鏂囨湰鏈€闀跨殑鎺т欢
                    best = None
                    best_len = -1
                    for c in candidates or []:
                        try:
                            t = c.window_text()
                            if t and len(t) > best_len:
                                best = c; best_len = len(t)
                        except Exception:
                            continue
                    if best is not None:
                        ctrl = best
                        try:
                            baseline = best.window_text()
                        except Exception:
                            baseline = ''
            except Exception:
                ctrl = None
        # Degraded path: resolve monitor via main window control_type='Text'.
        if ctrl is None:
            try:
                ctrl = self.win.child_window(control_type="Text")
                baseline = ctrl.window_text()
            except Exception:
                baseline = self.win.window_text()
                ctrl = None
        # Log baseline snapshot (truncated).
        try:
            parent_key = str(getattr(self.cfg, 'monitor_parent', 'info') or 'info')
            bl = (baseline or '')
            bl_disp = bl.replace('\r', ' ').replace('\n', ' ')
            if len(bl_disp) > 120:
                bl_disp = bl_disp[:117] + '...'
            h = None
            try:
                h = int(getattr(ctrl, 'handle', getattr(ctrl, 'element_info').handle)) if ctrl is not None else None
            except Exception:
                h = None
            print(f"[mon] baseline: parent={parent_key} class={cls_name} index={found_idx} hwnd={hex(h) if h else h} text='{bl_disp}'")
        except Exception:
            pass
        return ctrl, str(baseline or '')

    def wait_monitor_updated(self, timeout: float, baseline: Optional[str] = None) -> bool:
        ctrl = None
        if baseline is None:
            ctrl, baseline = self._capture_monitor_text()
        else:
            # If baseline is provided, still resolve control for polling.
            try:
                ctrl, _ = self._capture_monitor_text()
            except Exception:
                ctrl = None

        start = time.time()
        last_logged = start
        while time.time() - start < timeout:
            self._sleep(0.3)
            try:
                now = ctrl.window_text() if ctrl is not None else self.win.window_text()
            except Exception:
                now = self.win.window_text()
            now_s = str(now)
            if now_s != str(baseline):
                try:
                    nd = now_s.replace('\r', ' ').replace('\n', ' ')
                    if len(nd) > 120:
                        nd = nd[:117] + '...'
                    print(f"[mon] updated: text='{nd}'")
                except Exception:
                    pass
                print("[drv] monitor updated")
                return True
            # Log current value about every 1s to diagnose monitor target resolution.
            if time.time() - last_logged > 1.0:
                try:
                    nd = now_s.replace('\r', ' ').replace('\n', ' ')
                    if len(nd) > 120:
                        nd = nd[:117] + '...'
                    print(f"[mon] current: text='{nd}'")
                except Exception:
                    pass
                last_logged = time.time()
        print("[drv] monitor wait timeout")
        return False

    def run_once(self, charfile: str, sortie: str) -> bool:
        self.ensure_app()
        self.open_char_file(charfile)
        self.fill_sortie(sortie)
        self.insert_text_at_tail(charfile)
        self.transmit()
        return self.wait_monitor_updated(self.cfg.monitor_timeout_s)

    # --- helpers ---
    def set_date(self, ymd: str) -> None:
        frm = self._frame('realtime')
        try:
            self._textbox_by_index(frm, 0).set_edit_text(ymd)
        except Exception:
            # fallback not available; skip
            pass

    def set_time(self, hms: str) -> None:
        frm = self._frame('realtime')
        try:
            self._textbox_by_index(frm, 1).set_edit_text(hms)
        except Exception:
            try:
                self._textbox_by_index(frm, 2).set_edit_text(hms)
            except Exception:
                # fallback not available; skip
                pass

    def set_serial(self, serial: str) -> None:
        frm = self._frame('realtime')
        try:
            self._textbox_by_index(frm, 3).set_edit_text(serial)
        except Exception:
            pass

    def select_height(self, value: str) -> None:
        frm = self._frame('realtime')
        cmb = self._combo_by_index(frm, 0).wrapper_object()
        try:
            cmb.select(value)
        except Exception:
            try:
                send_keys(value)
            except Exception:
                pass

    def fill_matrix(self, toggles: List[Tuple[int, int]]) -> None:
        frm = self._frame('info')
        grid = self._grid(frm).wrapper_object()
        try:
            grid.set_focus(); grid.click_input()
        except Exception:
            pass
        cur = (0, 0)
        for col, row in toggles:
            dx, dy = col - cur[0], row - cur[1]
            if dx > 0:
                send_keys('{RIGHT %d}' % dx)
            elif dx < 0:
                send_keys('{LEFT %d}' % (-dx))
            if dy > 0:
                send_keys('{DOWN %d}' % dy)
            elif dy < 0:
                send_keys('{UP %d}' % (-dy))
            send_keys(' ')
            cur = (col, row)





