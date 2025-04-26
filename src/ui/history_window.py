import sys
import os # Import os for path checking
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QMessageBox, QTextEdit, QLabel,
    QLineEdit, QComboBox, QHBoxLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QFont, QColor, QTextCursor, QTextCharFormat, QTextDocument 

# Import function to get history data
from src.utils.database_manager import get_all_history
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

        self._setup_ui()
        self._load_history_data() # Load data when the window is initialized
        self._apply_filters() # Apply initial filter state (show all)

    def _setup_ui(self):
        """Sets up the UI elements for the history window."""
        # --- History Table --- 
        self.history_table = QTableWidget()
        self.layout.addWidget(self.history_table)

        # Define table columns
        self.column_headers = ["时间戳", "图片路径", "标牌文字", "喷码文字", "相似度", "结果"]
        self.history_table.setColumnCount(len(self.column_headers))
        self.history_table.setHorizontalHeaderLabels(self.column_headers)
        
        # Table properties
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers) # Read-only
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows) # Select whole rows
        self.history_table.setAlternatingRowColors(True) # Alternate row colors for readability
        self.history_table.verticalHeader().setVisible(False) # Hide row numbers

        # Adjust column widths
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # Timestamp
        header.setSectionResizeMode(1, QHeaderView.Stretch) # Image Path (stretch) 
        header.setSectionResizeMode(2, QHeaderView.Stretch) # Sign Text
        header.setSectionResizeMode(3, QHeaderView.Stretch) # Print Text
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # Similarity
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents) # Result

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

        self.history_table.setRowCount(0) # Clear existing rows
        self.history_table.setRowCount(len(history_data))

        for row_idx, row_data in enumerate(history_data):
            # Format similarity as percentage
            try:
                similarity_val = float(row_data[4]) # Assuming similarity is at index 4
                similarity_str = f"{similarity_val:.2%}"
            except (ValueError, TypeError):
                similarity_str = str(row_data[4]) # Fallback if conversion fails
            
            # Create QTableWidgetItem for each cell
            timestamp_item = QTableWidgetItem(str(row_data[0]))
            
            image_path_item = QTableWidgetItem(str(row_data[1]))
            # Style the image path item to look like a link
            link_font = QFont()
            link_font.setUnderline(True)
            image_path_item.setFont(link_font)
            image_path_item.setForeground(QColor('blue'))
            self.history_table.setItem(row_idx, 1, image_path_item)
            
            sign_text_raw = str(row_data[2])
            print_text_raw = str(row_data[3])
            
            # --- Use QTextEdit for RichText (HTML) display --- 
            sign_html, print_html = self.comparator.format_diff_html(sign_text_raw, print_text_raw)
            
            # Create QTextEdit for sign text
            sign_text_edit = QTextEdit()
            sign_text_edit.setReadOnly(True) # Make it non-editable
            sign_text_edit.setHtml(sign_html) # Set content using HTML
            # Style to blend in: remove border, transparent background
            sign_text_edit.setStyleSheet("QTextEdit { border: none; background-color: transparent; }")
            self.history_table.setCellWidget(row_idx, 2, sign_text_edit)
            
            # Create QTextEdit for print text
            print_text_edit = QTextEdit()
            print_text_edit.setReadOnly(True)
            print_text_edit.setHtml(print_html)
            print_text_edit.setStyleSheet("QTextEdit { border: none; background-color: transparent; }")
            self.history_table.setCellWidget(row_idx, 3, print_text_edit)
            
            similarity_item = QTableWidgetItem(similarity_str)
            result_item = QTableWidgetItem(str(row_data[5]))
            
            # Set items in the table row
            self.history_table.setItem(row_idx, 0, timestamp_item)
            self.history_table.setItem(row_idx, 4, similarity_item)
            self.history_table.setItem(row_idx, 5, result_item)

    def _apply_filters(self):
        """Applies search and filter criteria to the history table."""
        search_term = self.search_input.text().lower()
        filter_text = self.filter_combo.currentText()

        for row in range(self.history_table.rowCount()):
            sign_widget = self.history_table.cellWidget(row, 2)
            print_widget = self.history_table.cellWidget(row, 3)
            result_item = self.history_table.item(row, 5)

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
        columns_to_highlight = [2, 3] # Sign Text, Print Text

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
        # Check if the image path column (index 1) was clicked
        if column == 1:
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
