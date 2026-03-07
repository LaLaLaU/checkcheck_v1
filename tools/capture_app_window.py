#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Attach to the running CheckCheck app and capture a screenshot of the main window.
Usage:
  env\python.exe tools\capture_app_window.py [PID]
Saves to captures/app_window.png and prints the output path on success.
"""

import sys
import time
import os
from pywinauto import Application


def capture(pid=None) -> str:
    last_err = None
    # Give app some time to render the first window
    time.sleep(1.0)
    for backend in ("uia", "win32"):
        try:
            target = None
            if pid:
                app = Application(backend=backend).connect(process=pid, timeout=10)
                wins = app.windows()
                if wins:
                    for w in wins:
                        title = w.window_text() or ""
                        if ("CheckCheck" in title) or ("核对系统" in title):
                            target = w
                            break
                    if target is None:
                        target = wins[0]
                else:
                    last_err = RuntimeError("No windows found for process")
                    continue
            else:
                # Multiple top-level windows may exist; query Desktop directly
                from pywinauto import Desktop
                desktop = Desktop(backend=backend)
                wins = desktop.windows(title_re=r".*CheckCheck.*")
                if not wins:
                    last_err = RuntimeError("No windows matched title")
                    continue
                target = wins[0]
            time.sleep(0.5)
            img = target.capture_as_image()
            outdir = os.path.join(os.getcwd(), "captures")
            os.makedirs(outdir, exist_ok=True)
            outfile = os.path.join(outdir, "app_window.png")
            img.save(outfile)
            return outfile
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    raise SystemExit(f"capture failed: {last_err}")


def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    path = capture(pid)
    print(path)


if __name__ == "__main__":
    main()
