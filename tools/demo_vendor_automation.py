#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
离线冒烟测试脚本：验证与喷码应用的自动化连通性

运行方式（在 delivery_offline 目录）：
  - 双击 start_demo.bat（推荐，自动使用本地 env\python.exe）
  - 或 env\python.exe tools\demo_vendor_automation.py --help
"""

import argparse
import datetime as _dt
import os
import sys


def _ensure_repo_on_path():
    here = os.path.abspath(os.path.dirname(__file__))
    cur = here
    repo_root = None
    for _ in range(6):
        candidate = os.path.join(cur, 'src')
        if os.path.isdir(candidate):
            repo_root = cur
            break
        parent = os.path.abspath(os.path.join(cur, os.pardir))
        if parent == cur:
            break
        cur = parent
    if repo_root and repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def main():
    _ensure_repo_on_path()

    from src.utils.vendor_ui_driver import VendorUIDriver, UIDriverConfig
    from src.utils.config import get_char_root
    from src.utils.charfile_parser import get_metrics_with_cache
    from src.utils.charfile_matcher import find_best_charfile

    parser = argparse.ArgumentParser(description="CheckCheck Vendor UI Automation Smoke Test")
    parser.add_argument('--exe', dest='exe_path', default=None, help='喷码应用 exe 路径（已运行可不填）')
    parser.add_argument('--title-re', dest='title_re', default=r'.*(VJ-RT1|WH-VJ1000).*', help='顶层窗口标题正则')
    parser.add_argument('--charfile', dest='charfile', default=None, help='可选：字符文件路径')
    parser.add_argument('--sortie', dest='sortie', default='SG100', help='演示用文本（插入元素区第一个输入框）')
    parser.add_argument('--main', dest='main_code', default=None, help='可选：用于匹配字符文件的图号（如 J11B.5324.B.655.971）')
    parser.add_argument('--serial', dest='serial', default=None, help='可选：序列号（实时元素区），默认不设置')
    parser.add_argument('--height', dest='height', default=None, help='可选：喷码高度（如 8/32）')
    parser.add_argument('--set-rt-init', dest='set_rt_init', action='store_true', help='设置日期/时间/序列号')
    parser.add_argument('--timeout', dest='timeout', type=float, default=3.0, help='等待监控更新的超时（秒），默认 3s')
    parser.add_argument('--x-margin', dest='x_margin', type=int, default=None, help='靠右点击的水平边距像素（默认 20）')
    parser.add_argument('--sleep-scale', dest='sleep_scale', type=float, default=None, help='全局 sleep 缩放（如 0.5 更快）')
    parser.add_argument('--grid-wait', dest='grid_wait', type=float, default=None, help='滚动前稳定等待超时（秒），如 0.3 更快')
    parser.add_argument('--page-only', dest='page_only', action='store_true', help='仅翻页不做逐行精调（R=0）')
    parser.add_argument('--tail-ratio', dest='tail_ratio', type=float, default=None, help='列内水平比例 0.0..1.0（越小越靠左，默认 0.45）')
    parser.add_argument('--tail-left', dest='tail_left', type=int, default=None, help='相对内容列向左再偏移的列数（默认 0）')
    parser.add_argument('--viewport-cols', dest='viewport_cols', type=int, default=None, help='视窗可见列数 W（默认 123，调大等效“单页更宽”）')
    args = parser.parse_args()

    # 统一解析字符文件路径：严格模式（仅精确文件名）
    DEFAULT_BASENAME = 'J11B.5324.B.655.971'
    if not args.charfile:
        DEFAULT_BASENAME = 'J11B.5324.B.655.971'
        # 优先：repo 根目录下的该文件
        here = os.path.abspath(os.path.dirname(__file__))
        repo_chars = os.path.abspath(os.path.join(here, os.pardir, 'chars'))
        candidate = os.path.join(repo_chars, DEFAULT_BASENAME)
        if os.path.exists(candidate):
            args.charfile = os.path.abspath(candidate)
        else:
            # repo 内未命中时，允许在 repo_chars 下按“忽略扩展名”严格查找
            for dp, _, fns in os.walk(repo_chars):
                for fn in fns:
                    fn_low = fn.lower()
                    if fn_low == DEFAULT_BASENAME.lower():
                        args.charfile = os.path.join(dp, fn)
                        break
                    name, ext = os.path.splitext(fn_low)
                    if name == DEFAULT_BASENAME.lower():
                        args.charfile = os.path.join(dp, fn)
                        break
                if args.charfile:
                    break
            # 其次：根据配置/环境变量中的字符根目录，严格查找该文件名（忽略扩展）
            root = get_char_root()
            root_abs = os.path.abspath(root)
            if os.path.isdir(root_abs):
                # 精确查找 basename
                for dp, _, fns in os.walk(root_abs):
                    for fn in fns:
                        fn_low = fn.lower()
                        if fn_low == DEFAULT_BASENAME.lower():
                            args.charfile = os.path.join(dp, fn)
                            break
                        name, ext = os.path.splitext(fn_low)
                        if name == DEFAULT_BASENAME.lower():
                            args.charfile = os.path.join(dp, fn)
                            break
                    if args.charfile:
                        break

    cfg = UIDriverConfig(exe_path=args.exe_path, title_re=args.title_re, monitor_timeout_s=args.timeout)
    if args.x_margin is not None:
        cfg.x_margin_px = args.x_margin
    if args.sleep_scale is not None:
        setattr(cfg, 'sleep_scale', args.sleep_scale)
    if args.grid_wait is not None:
        setattr(cfg, 'grid_wait_timeout_s', args.grid_wait)
    if args.page_only:
        setattr(cfg, 'page_only', True)
    if args.tail_ratio is not None:
        setattr(cfg, 'tail_click_inner_ratio', float(args.tail_ratio))
    if args.tail_left is not None:
        setattr(cfg, 'tail_click_extra_left_cols', int(args.tail_left))
    if args.viewport_cols is not None and args.viewport_cols > 0:
        setattr(cfg, 'viewport_cols', int(args.viewport_cols))

    drv = VendorUIDriver(cfg)

    # 若传入的是目录，则在该目录内严格查找默认文件名
    if args.charfile and os.path.isdir(args.charfile):
        search_root = args.charfile
        resolved = None
        # 先找默认基名（忽略扩展）
        cand = os.path.join(search_root, DEFAULT_BASENAME)
        if os.path.exists(cand):
            resolved = cand
        else:
            for dp, _, fns in os.walk(search_root):
                for fn in fns:
                    fn_low = fn.lower()
                    if fn_low == DEFAULT_BASENAME.lower():
                        resolved = os.path.join(dp, fn)
                        break
                    name, ext = os.path.splitext(fn_low)
                    if name == DEFAULT_BASENAME.lower():
                        resolved = os.path.join(dp, fn)
                        break
                if resolved:
                    break
        if resolved:
            args.charfile = os.path.abspath(resolved)
        else:
            # 严格：未找到精确文件名则视为未提供
            args.charfile = None

    # 若仍未解析且提供了 main_code，则尝试基于索引/扫描严格匹配该 code
    if not args.charfile and args.main_code:
        best, score = find_best_charfile(args.main_code, use_index=True, allow_scan=True, fuzzy_threshold=1.0)
        if best:
            args.charfile = str(best)

    print("[demo] 参数汇总:")
    print(f"  exe={args.exe_path}")
    print(f"  title_re={args.title_re}")
    print(f"  charfile={args.charfile}")
    print(f"  timeout={args.timeout}s")
    if args.charfile:
        try:
            m = get_metrics_with_cache(args.charfile)
            print(f"  metrics: top_row={m.top_row} scroll_percent={m.scroll_percent}")
        except Exception as _e:
            print(f"  metrics: <error> {_e}")
    else:
        if args.main_code:
            print(f"  <warn> 按图号严格匹配失败: {args.main_code}")
        print(f"  <warn> 未找到严格匹配的字符文件 '{DEFAULT_BASENAME}'，将跳过‘载入字符文件’步骤。可用 --charfile 指定完整路径，或提供 --main 与已构建索引匹配。")

    print("[demo] 连接/启动应用...")
    drv.ensure_app()

    if args.set_rt_init:
        today = _dt.datetime.now()
        ymd = today.strftime('%Y/%m/%d')
        hms = today.strftime('%H:%M:%S')
        print(f"[demo] 设置日期={ymd} 时间={hms} 序列号={args.serial or '<skip>'}")
        try:
            drv.set_date(ymd)
        except Exception as e:
            print(f"[warn] set_date 失败: {e}")
        try:
            drv.set_time(hms)
        except Exception as e:
            print(f"[warn] set_time 失败: {e}")
        if args.serial:
            try:
                drv.set_serial(args.serial)
            except Exception as e:
                print(f"[warn] set_serial 失败: {e}")
        if args.height:
            try:
                drv.select_height(args.height)
            except Exception as e:
                print(f"[warn] select_height 失败: {e}")

    if args.charfile:
        print(f"[demo] 载入字符文件: {args.charfile}")
        try:
            drv.open_char_file(args.charfile)
        except Exception as e:
            print(f"[warn] 载入字符文件失败: {e}")

    print(f"[demo] 插入元素区输入: {args.sortie}")
    try:
        drv.fill_sortie(args.sortie)
    except Exception as e:
        print(f"[warn] fill_sortie 失败: {e}")

    if args.charfile:
        print("[demo] 在尾部插入文字...")
        try:
            drv.insert_text_at_tail(args.charfile)
        except Exception as e:
            print(f"[warn] insert_text_at_tail 失败: {e}")

    print("[demo] 传输信息...")
    try:
        drv.transmit()
    except Exception as e:
        print(f"[warn] transmit 失败: {e}")

    print("[demo] 结果: OK (monitor skipped)")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as _e:
        print(f"[fatal] 异常: {_e}")
        sys.exit(2)
