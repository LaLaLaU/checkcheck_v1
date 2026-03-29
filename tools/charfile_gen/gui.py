#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gen_charfile import DEFAULT_LINE1, DEFAULT_LINE2, generate_charfile, preload_wqy_bitmap_fonts


def _default_out_dir() -> str:
    try:
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from src.utils.config import get_char_root

        root = Path(get_char_root() or "")
        if not root:
            raise RuntimeError("empty char_root")
        if not root.is_absolute():
            root = (repo_root / root).resolve()
        return str(root / "_生成")
    except Exception:
        return str(Path("打码机管子汇总") / "_生成")


class CharfileGenWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("字符文件生成器")
        self.resize(1280, 860)
        self._setup_ui()
        self._start_font_warmup()

    def _setup_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        form_group = QGroupBox("输入与参数")
        form_group.setFont(QFont("", 11, QFont.Bold))
        form = QFormLayout(form_group)
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)

        self.cn_edit = QLineEdit("燃油")
        self.cn_edit.setPlaceholderText("汉字前缀（可空）")
        form.addRow("汉字前缀:", self.cn_edit)

        self.code_edit = QLineEdit("J11B.6130.B.505.919")
        self.code_edit.setPlaceholderText("图号（将作为输出文件名）")
        form.addRow("图号:", self.code_edit)

        self.out_dir_edit = QLineEdit(_default_out_dir())
        out_row = QHBoxLayout()
        out_row.addWidget(self.out_dir_edit, 1)
        btn_browse_out = QPushButton("选择目录")
        btn_browse_out.clicked.connect(self._pick_out_dir)
        out_row.addWidget(btn_browse_out)
        out_box = QWidget()
        out_box.setLayout(out_row)
        form.addRow("输出目录:", out_box)

        self.bold_checkbox = QCheckBox("使用加粗字库（wenquanyi_12ptb.pcf）")
        self.bold_checkbox.setChecked(False)
        form.addRow("字库样式:", self.bold_checkbox)

        self.center_punctuation_checkbox = QCheckBox("标点居中")
        self.center_punctuation_checkbox.setChecked(False)
        form.addRow("标点样式:", self.center_punctuation_checkbox)

        self.line1_edit = QLineEdit(DEFAULT_LINE1)
        self.line2_edit = QLineEdit(DEFAULT_LINE2)
        form.addRow("头1:", self.line1_edit)
        form.addRow("头2:", self.line2_edit)

        gap_row = QHBoxLayout()
        self.gap_cn_code_spin = QSpinBox()
        self.gap_cn_code_spin.setRange(0, 100)
        self.gap_cn_code_spin.setValue(9)
        self.gap_code_spin = QSpinBox()
        self.gap_code_spin.setRange(0, 100)
        self.gap_code_spin.setValue(2)
        self.gap_dot_spin = QSpinBox()
        self.gap_dot_spin.setRange(0, 100)
        self.gap_dot_spin.setValue(2)
        self.gap_cn_inner_spin = QSpinBox()
        self.gap_cn_inner_spin.setRange(0, 100)
        self.gap_cn_inner_spin.setValue(1)

        gap_row.addWidget(QLabel("汉字-图号"))
        gap_row.addWidget(self.gap_cn_code_spin)
        gap_row.addSpacing(8)
        gap_row.addWidget(QLabel("图号普通"))
        gap_row.addWidget(self.gap_code_spin)
        gap_row.addSpacing(8)
        gap_row.addWidget(QLabel("点号边界"))
        gap_row.addWidget(self.gap_dot_spin)
        gap_row.addSpacing(8)
        gap_row.addWidget(QLabel("汉字内部"))
        gap_row.addWidget(self.gap_cn_inner_spin)
        gap_row.addStretch(1)

        gap_box = QWidget()
        gap_box.setLayout(gap_row)
        form.addRow("间距(列):", gap_box)

        self.preview_checkbox = QCheckBox("生成预览图文件")
        self.preview_checkbox.setChecked(False)
        form.addRow("预览输出:", self.preview_checkbox)

        root.addWidget(form_group)

        btn_row = QHBoxLayout()
        self.generate_btn = QPushButton("生成字符文件")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.generate_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self.generate_btn)

        self.open_dir_btn = QPushButton("打开输出目录")
        self.open_dir_btn.setMinimumHeight(40)
        self.open_dir_btn.clicked.connect(self._open_out_dir)
        btn_row.addWidget(self.open_dir_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.status_label = QLabel("状态: 等待生成")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.status_label)

        self.out_label = QLabel("输出文件: <未生成>")
        self.out_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.out_label)

        preview_group = QGroupBox("预览")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_label = QLabel("生成后会在此显示预览")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(280)
        self.preview_label.setStyleSheet("border:1px solid #d9d9d9; background:#fafafa;")
        self.preview_scroll.setWidget(self.preview_label)
        preview_layout.addWidget(self.preview_scroll)
        root.addWidget(preview_group, 1)

    def _start_font_warmup(self) -> None:
        def _warmup() -> None:
            try:
                preload_wqy_bitmap_fonts()
            except Exception:
                # Warmup is best-effort. Generation will still load lazily if needed.
                pass

        self._warmup_thread = threading.Thread(target=_warmup, name="charfile-font-warmup", daemon=True)
        self._warmup_thread.start()

    def _pick_out_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir_edit.text().strip() or ".")
        if path:
            self.out_dir_edit.setText(path)

    def _open_out_dir(self) -> None:
        out_dir = self.out_dir_edit.text().strip()
        if not out_dir:
            return
        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(p))  # type: ignore[attr-defined]
        except Exception as e:
            QMessageBox.warning(self, "打开目录失败", str(e))

    def _apply_preview_pixmap(self, pix: QPixmap) -> None:
        if pix.isNull():
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("预览读取失败")
            return
        max_w = 2400
        if pix.width() > max_w:
            pix = pix.scaledToWidth(max_w, mode=Qt.FastTransformation)
        self.preview_label.setPixmap(pix)
        self.preview_label.adjustSize()

    def _show_preview(self, path: Path) -> None:
        self._apply_preview_pixmap(QPixmap(str(path)))

    def _show_preview_from_charfile(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            cols = [ln.strip() for ln in lines[2:] if ln.strip()]
            if not cols:
                raise RuntimeError("empty columns")

            h = 16
            w = len(cols)
            img = QImage(w, h, QImage.Format_Grayscale8)
            img.fill(255)
            for x, col in enumerate(cols):
                if len(col) != h:
                    continue
                for y, bit in enumerate(col):
                    if bit == "1":
                        img.setPixel(x, y, 0)

            scale = 16
            img = img.scaled(w * scale, h * scale, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            self._apply_preview_pixmap(QPixmap.fromImage(img))
        except Exception:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("预览读取失败")

    def _on_generate(self) -> None:
        try:
            code = self.code_edit.text().strip()
            if not code:
                QMessageBox.warning(self, "参数错误", "图号不能为空。")
                return

            out_dir = self.out_dir_edit.text().strip() or "chars/generated"
            want_preview_file = bool(self.preview_checkbox.isChecked())

            result = generate_charfile(
                cn=self.cn_edit.text().strip(),
                code=code,
                out_dir=out_dir,
                output=None,
                bold=bool(self.bold_checkbox.isChecked()),
                center_punctuation=bool(self.center_punctuation_checkbox.isChecked()),
                line1=self.line1_edit.text().strip() or DEFAULT_LINE1,
                line2=self.line2_edit.text().strip() or DEFAULT_LINE2,
                gap_cn_code=int(self.gap_cn_code_spin.value()),
                gap_code=int(self.gap_code_spin.value()),
                gap_dot=int(self.gap_dot_spin.value()),
                gap_cn_inner=int(self.gap_cn_inner_spin.value()),
                save_preview=want_preview_file,
                preview=None,
            )

            self.status_label.setText(f"状态: 生成成功，列数 {result.columns}")
            self.out_label.setText(f"输出文件: {result.out_path}")

            # Always show preview in UI, even when preview file is not requested.
            if result.preview_path is not None:
                self._show_preview(result.preview_path)
            else:
                self._show_preview_from_charfile(result.out_path)
        except Exception as e:
            self.status_label.setText(f"状态: 生成失败 - {e}")
            QMessageBox.critical(self, "生成失败", str(e))


def main() -> int:
    app = QApplication(sys.argv)
    win = CharfileGenWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
