import sys
import os # Import os for path checking
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QMessageBox, QTextEdit, QLabel,
    QLineEdit, QComboBox, QHBoxLayout, QPushButton
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QFont, QColor, QTextCursor, QTextCharFormat, QTextDocument 

# Import function to get history data
from src.utils.database_manager import get_all_history, delete_history_records
from src.core.text_comparator import TextComparator

class HistoryWindow(QDialog):
    """Dialog window to display recognition history."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("识别历史记录")
        self.setMinimumSize(800, 400) # Set a minimum size

        self.comparator = TextComparator()

        # --- Layouts --- 
        self.layout = QVBoxLayout(self)
        filter_layout = QHBoxLayout() # Layout for filters

        # --- Filter Widgets --- 
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索标牌或喷码文字...")
        self.search_input.textChanged.connect(self._apply_filters) 
 
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(['全部', '通过', '不通过'])
        self.filter_combo.currentIndexChanged.connect(self._apply_filters)

        filter_layout.addWidget(QLabel("搜索:"))
        filter_layout.addWidget(self.search_input)
        filter_layout.addWidget(QLabel("结果:"))
        filter_layout.addWidget(self.filter_combo)

        self.layout.addLayout(filter_layout) # Add filter layout to main layout

        # 操作区：多选操作 + 删除所选记录
        action_layout = QHBoxLayout()
        self.delete_button = QPushButton("仅删记录")
        self.delete_button.setToolTip("只从数据库删除所选记录，不删除本地图片")
        self.delete_button.clicked.connect(lambda: self._delete_selected_rows(delete_files=False))

        self.delete_with_files_button = QPushButton("删记录+文件")
        self.delete_with_files_button.setToolTip("从数据库删除所选记录，并同时删除其对应的本地图片文件")
        self.delete_with_files_button.clicked.connect(lambda: self._delete_selected_rows(delete_files=True))
        # 全选/全不选/反选
        self.select_all_button = QPushButton("全选")
        self.select_all_button.clicked.connect(lambda: self._set_all_checks(True))
        self.select_none_button = QPushButton("全不选")
        self.select_none_button.clicked.connect(lambda: self._set_all_checks(False))
        self.invert_select_button = QPushButton("反选")
        self.invert_select_button.clicked.connect(self._invert_checks)
        action_layout.addWidget(self.select_all_button)
        action_layout.addWidget(self.select_none_button)
        action_layout.addWidget(self.invert_select_button)
        action_layout.addWidget(self.delete_button)
        action_layout.addWidget(self.delete_with_files_button)
        action_layout.addStretch(1)
        self.layout.addLayout(action_layout)

        self._setup_ui()
        self._load_history_data() # Load data when the window is initialized
        self._apply_filters() # Apply initial filter state (show all)

    def _setup_ui(self):
        """Sets up the UI elements for the history window."""
        # --- History Table --- 
        self.history_table = QTableWidget()
        self.layout.addWidget(self.history_table)

        # Define table columns（新增第0列：选择框）
        self.column_headers = ["选择", "时间戳", "图片路径", "标牌文字", "喷码文字", "相似度", "结果"]
        self.history_table.setColumnCount(len(self.column_headers))
        self.history_table.setHorizontalHeaderLabels(self.column_headers)
        
        # Table properties
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setSelectionMode(QTableWidget.ExtendedSelection)

        # Adjust column widths
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 选择
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 时间戳
        header.setSectionResizeMode(2, QHeaderView.Stretch)           # 图片路径
        header.setSectionResizeMode(3, QHeaderView.Stretch)           # 标牌文字
        header.setSectionResizeMode(4, QHeaderView.Stretch)           # 喷码文字
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # 相似度
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # 结果

        # Connect cell click signal
        self.history_table.cellClicked.connect(self._on_cell_clicked)

    def _load_history_data(self):
        """Loads data from the database and populates the table."""
        try:
            history_data = get_all_history()
        except Exception as e:
            # In a real app, show a proper message box or log
            print(f"Error loading history: {e}") 
            # For now, just show an empty table if error occurs
            history_data = [] 

        self.history_table.setRowCount(0)
        self.history_table.setRowCount(len(history_data))

        for row_idx, row_data in enumerate(history_data):
            # Format similarity as percentage
            try:
                similarity_val = float(row_data[4])
                similarity_str = f"{similarity_val:.2%}"
            except (ValueError, TypeError):
                similarity_str = str(row_data[4])
            
            # 第0列：选择复选框
            select_item = QTableWidgetItem()
            select_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            select_item.setCheckState(Qt.Unchecked)
            self.history_table.setItem(row_idx, 0, select_item)

            # 其余列右移一位
            timestamp_item = QTableWidgetItem(str(row_data[0]))
            image_path_item = QTableWidgetItem(str(row_data[1]))
            link_font = QFont()
            link_font.setUnderline(True)
            image_path_item.setFont(link_font)
            image_path_item.setForeground(QColor('blue'))
            self.history_table.setItem(row_idx, 2, image_path_item)

            sign_text_raw = str(row_data[2])
            print_text_raw = str(row_data[3])

            sign_html, print_html = self.comparator.format_diff_html(sign_text_raw, print_text_raw)

            sign_text_edit = QTextEdit()
            sign_text_edit.setReadOnly(True)
            sign_text_edit.setHtml(sign_html)
            sign_text_edit.setStyleSheet("QTextEdit { border: none; background-color: transparent; }")
            self.history_table.setCellWidget(row_idx, 3, sign_text_edit)

            print_text_edit = QTextEdit()
            print_text_edit.setReadOnly(True)
            print_text_edit.setHtml(print_html)
            print_text_edit.setStyleSheet("QTextEdit { border: none; background-color: transparent; }")
            self.history_table.setCellWidget(row_idx, 4, print_text_edit)

            similarity_item = QTableWidgetItem(similarity_str)
            result_item = QTableWidgetItem(str(row_data[5]))

            self.history_table.setItem(row_idx, 1, timestamp_item)
            self.history_table.setItem(row_idx, 5, similarity_item)
            self.history_table.setItem(row_idx, 6, result_item)

    def _delete_selected_rows(self, delete_files: bool = False):
        # 优先按勾选行删除；若无勾选，则按表格选择行删除
        rows = self._get_checked_rows()
        if not rows:
            rows = sorted({i.row() for i in self.history_table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要删除的记录")
            return
        keys = []
        image_paths = []
        for r in rows:
            timestamp = self.history_table.item(r, 1).text() if self.history_table.item(r,1) else ""
            image_path = self.history_table.item(r, 2).text() if self.history_table.item(r,2) else ""
            sign_widget = self.history_table.cellWidget(r, 3)
            print_widget = self.history_table.cellWidget(r, 4)
            sign_text = sign_widget.toPlainText() if sign_widget else ""
            print_text = print_widget.toPlainText() if print_widget else ""
            keys.append((timestamp, image_path, sign_text, print_text))
            image_paths.append(image_path)

        tip = "同时删除本地文件" if delete_files else "仅删除记录"
        confirm = QMessageBox.question(self, "确认删除", f"将{tip}：{len(rows)} 条，操作不可恢复，确定吗？")
        if confirm != QMessageBox.Yes:
            return
        try:
            delete_history_records(keys)
            for r in rows:
                self.history_table.removeRow(r)
            if delete_files:
                removed, failed = 0, 0
                for p in image_paths:
                    try:
                        if p and os.path.exists(p):
                            os.remove(p)
                            removed += 1
                    except Exception:
                        failed += 1
                if failed:
                    QMessageBox.warning(self, "文件删除部分失败", f"已删除 {removed} 张图片，{failed} 张删除失败。")
        except Exception as e:
            QMessageBox.critical(self, "删除失败", f"删除时出错：{e}")

    def _get_checked_rows(self):
        rows = []
        for r in range(self.history_table.rowCount()):
            item = self.history_table.item(r, 0)
            if item and item.checkState() == Qt.Checked:
                rows.append(r)
        return sorted(rows, reverse=True)

    def _set_all_checks(self, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        for r in range(self.history_table.rowCount()):
            item = self.history_table.item(r, 0)
            if item:
                item.setCheckState(state)

    def _invert_checks(self):
        for r in range(self.history_table.rowCount()):
            item = self.history_table.item(r, 0)
            if item:
                item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def _apply_filters(self):
        """Applies search and filter criteria to the history table."""
        search_term = self.search_input.text().lower()
        filter_text = self.filter_combo.currentText()

        for row in range(self.history_table.rowCount()):
            sign_widget = self.history_table.cellWidget(row, 3)
            print_widget = self.history_table.cellWidget(row, 4)
            result_item = self.history_table.item(row, 6)

            if not sign_widget or not print_widget or not result_item: # Should not happen
                continue

            sign_text = sign_widget.toPlainText().lower()
            print_text = print_widget.toPlainText().lower()
            result_text = result_item.text()

            # Check search match
            search_match = (
                not search_term or 
                search_term in sign_text or 
                search_term in print_text
            )

            # Check filter match
            filter_match = (
                filter_text == '全部' or
                filter_text == result_text
            )

            # Set row visibility
            is_visible = search_match and filter_match
            self.history_table.setRowHidden(row, not is_visible)

            # Apply/clear highlight if row is visible
            if is_visible:
                self._highlight_text(row, self.search_input.text()) # Pass original case for highlighting
            # No need to explicitly clear highlight if hidden, but good practice if shown
            elif not is_visible and self.search_input.text(): # Ensure highlight clears if made visible again without search
                 self._highlight_text(row, "")

    def _highlight_text(self, row_index, search_term):
        """Highlights occurrences of search_term in sign and print columns for a given row."""
        columns_to_highlight = [3, 4] # Sign Text, Print Text

        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor("yellow"))

        clear_format = QTextCharFormat()
        clear_format.setBackground(Qt.transparent)

        for col_index in columns_to_highlight:
            widget = self.history_table.cellWidget(row_index, col_index)
            if isinstance(widget, QTextEdit):
                document = widget.document()
                cursor = QTextCursor(document)

                # --- Clear previous yellow background highlight --- 
                cursor.movePosition(QTextCursor.Start)
                cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
                cursor.mergeCharFormat(clear_format) # Apply transparent background

                # --- Apply new highlight if search_term is provided ---
                if search_term:
                    cursor.movePosition(QTextCursor.Start) # Reset cursor position
                    find_flags = QTextDocument.FindFlags() # Default is case-insensitive
                    while True:
                        cursor = document.find(search_term, cursor, find_flags)
                        if cursor.isNull():
                            break # No more occurrences found
                        # Apply yellow background to the found selection
                        cursor.mergeCharFormat(highlight_format) 

    def _on_cell_clicked(self, row, column):
        """Handles clicks on table cells."""
        # Check if the image path column (index 2) was clicked
        if column == 2:
            item = self.history_table.item(row, column)
            if item:
                image_path = item.text()
                self._show_image_preview(image_path)

    def _show_image_preview(self, image_path):
        """Shows the image preview dialog for the given path."""
        if not os.path.exists(image_path):
            QMessageBox.warning(self, "文件未找到", f"无法找到图片文件:\n{image_path}")
            return
        
        preview_dialog = ImagePreviewDialog(image_path, self)
        preview_dialog.exec_()

    def keyPressEvent(self, event):
        # 支持 Delete 键快捷删除
        try:
            if event.key() == Qt.Key_Delete:
                self._delete_selected_rows()
                return
        except Exception:
            pass
        super().keyPressEvent(event)


# Example usage (for testing the window layout)
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = HistoryWindow()
    window.show()
    sys.exit(app.exec_())


class ImagePreviewDialog(QDialog):
    """A simple dialog to display an image preview."""
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("图片预览")
        
        self.layout = QVBoxLayout(self)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.image_label)

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.image_label.setText(f"无法加载图片:\n{image_path}")
            self.setMinimumSize(300, 100)
        else:
            # Scale pixmap to fit reasonably, maintaining aspect ratio
            max_width = 800
            max_height = 600
            scaled_pixmap = pixmap.scaled(max_width, max_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
            # Adjust dialog size to pixmap size + some margin
            self.resize(scaled_pixmap.width() + 20, scaled_pixmap.height() + 40) 

        self.setLayout(self.layout)
