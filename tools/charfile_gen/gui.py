#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
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

from gen_charfile import DEFAULT_LINE1, DEFAULT_LINE2, generate_charfile


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

        self.font_edit = QLineEdit("")
        self.font_edit.setPlaceholderText("可选：字体路径（如 C:\\Windows\\Fonts\\msyh.ttc）")
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_edit, 1)
        btn_browse_font = QPushButton("选择字体")
        btn_browse_font.clicked.connect(self._pick_font)
        font_row.addWidget(btn_browse_font)
        font_box = QWidget()
        font_box.setLayout(font_row)
        form.addRow("字体文件:", font_box)

        self.line1_edit = QLineEdit(DEFAULT_LINE1)
        self.line2_edit = QLineEdit(DEFAULT_LINE2)
        form.addRow("头1:", self.line1_edit)
        form.addRow("头2:", self.line2_edit)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 300)
        self.font_size_spin.setValue(64)
        form.addRow("字体大小:", self.font_size_spin)

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 255)
        self.threshold_spin.setValue(180)
        form.addRow("二值阈值:", self.threshold_spin)

        gap_row = QHBoxLayout()
        self.gap_cn_code_spin = QSpinBox()
        self.gap_cn_code_spin.setRange(0, 100)
        self.gap_cn_code_spin.setValue(9)
        self.gap_code_spin = QSpinBox()
        self.gap_code_spin.setRange(0, 100)
        self.gap_code_spin.setValue(2)
        self.gap_dot_spin = QSpinBox()
        self.gap_dot_spin.setRange(0, 100)
        self.gap_dot_spin.setValue(3)
        self.gap_cn_inner_spin = QSpinBox()
        self.gap_cn_inner_spin.setRange(0, 100)
        self.gap_cn_inner_spin.setValue(0)
        gap_row.addWidget(QLabel("汉字-图号"))
        gap_row.addWidget(self.gap_cn_code_spin)
        gap_row.addSpacing(8)
        gap_row.addWidget(QLabel("图号普通"))
        gap_row.addWidget(self.gap_code_spin)
        gap_row.addSpacing(8)
        gap_row.addWidget(QLabel("点边界"))
        gap_row.addWidget(self.gap_dot_spin)
        gap_row.addSpacing(8)
        gap_row.addWidget(QLabel("汉字内部"))
        gap_row.addWidget(self.gap_cn_inner_spin)
        gap_row.addStretch(1)
        gap_box = QWidget()
        gap_box.setLayout(gap_row)
        form.addRow("间距(列):", gap_box)

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
        self.preview_label = QLabel("暂无预览")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(280)
        self.preview_label.setStyleSheet("border:1px solid #d9d9d9; background:#fafafa;")
        self.preview_scroll.setWidget(self.preview_label)
        preview_layout.addWidget(self.preview_scroll)
        root.addWidget(preview_group, 1)

    def _pick_out_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir_edit.text().strip() or ".")
        if path:
            self.out_dir_edit.setText(path)

    def _pick_font(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择字体文件",
            self.font_edit.text().strip() or r"C:\Windows\Fonts",
            "Font Files (*.ttf *.ttc *.otf);;All Files (*.*)",
        )
        if path:
            self.font_edit.setText(path)

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

    def _show_preview(self, path: Path) -> None:
        pix = QPixmap(str(path))
        if pix.isNull():
            self.preview_label.setText("预览读取失败")
            return
        max_w = 2400
        if pix.width() > max_w:
            pix = pix.scaledToWidth(max_w, mode=Qt.FastTransformation)
        self.preview_label.setPixmap(pix)
        self.preview_label.adjustSize()

    def _on_generate(self) -> None:
        try:
            code = self.code_edit.text().strip()
            if not code:
                QMessageBox.warning(self, "参数错误", "图号不能为空。")
                return

            out_dir = self.out_dir_edit.text().strip() or "chars/generated"
            preview_path = str(Path(out_dir) / f"{code}.png")

            result = generate_charfile(
                cn=self.cn_edit.text().strip(),
                code=code,
                out_dir=out_dir,
                output=None,
                font=self.font_edit.text().strip() or None,
                font_size=int(self.font_size_spin.value()),
                threshold=int(self.threshold_spin.value()),
                line1=self.line1_edit.text().strip() or DEFAULT_LINE1,
                line2=self.line2_edit.text().strip() or DEFAULT_LINE2,
                gap_cn_code=int(self.gap_cn_code_spin.value()),
                gap_code=int(self.gap_code_spin.value()),
                gap_dot=int(self.gap_dot_spin.value()),
                gap_cn_inner=int(self.gap_cn_inner_spin.value()),
                preview=preview_path,
            )

            self.status_label.setText(f"状态: 生成成功，列数={result.columns}")
            self.out_label.setText(f"输出文件: {result.out_path}")
            self._show_preview(result.preview_path)
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

