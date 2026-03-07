#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QHBoxLayout,
    QFileDialog, QDialogButtonBox, QLabel, QDoubleSpinBox
)
from PyQt5.QtCore import Qt

from src.utils.config import (
    get_char_root, get_match_threshold, get_vendor_exe, get_vendor_title_re, update_config
)
from src.utils.charfile_matcher import build_index, save_index


class SettingsDialog(QDialog):
    """应用设置：字符文件路径 + 匹配阈值 +（可选）喷码软件连接。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(520, 260)

        vbox = QVBoxLayout(self)
        form = QFormLayout()

        # 字符文件根目录
        self.char_root_edit = QLineEdit(get_char_root())
        btn_browse = QPushButton("选择…")
        btn_browse.clicked.connect(self._choose_char_root)
        row = QHBoxLayout()
        row.addWidget(self.char_root_edit)
        row.addWidget(btn_browse)
        form.addRow("字符文件路径:", row)

        # 匹配阈值 0.50 ~ 1.00
        self.thr_spin = QDoubleSpinBox()
        self.thr_spin.setDecimals(2)
        self.thr_spin.setRange(0.50, 1.00)
        self.thr_spin.setSingleStep(0.01)
        self.thr_spin.setValue(float(get_match_threshold()))
        form.addRow("匹配阈值:", self.thr_spin)

        # 喷码软件可执行路径（可选）
        self.exe_edit = QLineEdit(get_vendor_exe() or "")
        btn_exe = QPushButton("浏览…")
        btn_exe.clicked.connect(self._choose_exe)
        row2 = QHBoxLayout()
        row2.addWidget(self.exe_edit)
        row2.addWidget(btn_exe)
        form.addRow("喷码软件 exe(可选):", row2)

        # 窗口标题正则（可选）
        self.title_re_edit = QLineEdit(get_vendor_title_re() or r'.*(VJ-RT1|WH-VJ1000).*')
        form.addRow("窗口标题正则:", self.title_re_edit)

        vbox.addLayout(form)

        # 构建索引按钮
        self.build_btn = QPushButton("重建字符文件索引")
        self.build_btn.clicked.connect(self._rebuild_index)
        self.build_status = QLabel("")
        status_row = QHBoxLayout()
        status_row.addWidget(self.build_btn)
        status_row.addWidget(self.build_status)
        vbox.addLayout(status_row)

        # OK/Cancel
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        vbox.addWidget(btns)

    def _choose_char_root(self):
        path = QFileDialog.getExistingDirectory(self, "选择字符文件路径", self.char_root_edit.text() or "")
        if path:
            self.char_root_edit.setText(path)

    def _choose_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择喷码软件可执行文件", self.exe_edit.text() or "", "可执行文件 (*.exe);;所有文件 (*.*)")
        if path:
            self.exe_edit.setText(path)

    def _rebuild_index(self):
        root = self.char_root_edit.text().strip()
        try:
            mapping = build_index(root)
            save_index(mapping, None, root_dir=root)
            self.build_status.setText(f"已索引 {len(mapping)} 个文件")
        except Exception as e:
            self.build_status.setText(f"索引失败: {e}")

    def _accept(self):
        # 保存到配置
        update_config({
            'char_root': self.char_root_edit.text().strip(),
            'char_match_threshold': float(self.thr_spin.value()),
            'vendor_exe': self.exe_edit.text().strip() or None,
            'vendor_title_re': self.title_re_edit.text().strip() or None,
        })
        self.accept()

