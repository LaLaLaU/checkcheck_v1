# CheckCheck 项目当前问题记录

**日期**: 2025-04-28
**版本**: 1.1

## 功能问题与解决方案

### 1. 文本区分策略不合理

**问题描述**: 
当前代码简单地根据文本框Y坐标位置区分上下文本（标牌/喷码），这种方法不够灵活，无法适应不同图像布局。

**原因分析**:
在 `_recognize_current_frame` 方法中，使用了固定的Y坐标位置划分策略：
```python
# 假设上半部分是标牌文字，下半部分是喷码文字
height = self.cv_image.shape[0]
middle_y = height / 2
for item in text_with_positions:
    if center_y < middle_y:
        label_texts.append(text)
    else:
        print_texts.append(text)
```

**解决方案**:
1. 不预先区分标牌/喷码文字，而是将所有识别到的文本列出
2. 向UI中添加两个下拉列表或文本框，让用户可以选择或输入要比对的文本
3. 显示所有识别出的文本，例如：
```python
# 识别所有文本，不区分类型
all_detected_texts = []
for item in text_with_positions:
    box, text, confidence, center_y = item
    all_detected_texts.append((text, confidence))

# 显示所有文本供用户选择
self.detected_texts_label.setText("识别到的所有文本：\n" + "\n".join([f"{i+1}. {text} (置信度: {conf:.2f})" for i, (text, conf) in enumerate(all_detected_texts)]))

# 添加下拉选择框让用户指定
self.label_text_combo = QComboBox()
self.print_text_combo = QComboBox()
for text, _ in all_detected_texts:
    self.label_text_combo.addItem(text)
    self.print_text_combo.addItem(text)
```

### 2. 上传图片识别导致应用闪退

**问题描述**:
上传图片后点击识别按钮会导致应用程序崩溃。

**原因分析**:
分析代码发现两个明确的问题：

1. 在 `on_start_recognition` 方法（第402行）中使用了错误的变量类型：
```python
if not self.current_image or not os.path.exists(self.current_image):
```
这里 `self.current_image` 是 QPixmap 对象而非字符串路径，所以 `os.path.exists()` 会引发类型错误。

2. 在第417行进一步尝试使用 QPixmap 对象作为文件路径：
```python
img_data = cv2.imread(self.current_image)
```
同样会导致类型错误。

代码检查还发现，`load_image` 方法中正确设置了三个相关变量：
```python
self.image_path = image_path  # 字符串路径
self.current_image = pixmap   # QPixmap对象
self.cv_image = cv2.imread(image_path)  # OpenCV图像对象
```
但 `on_start_recognition` 没有正确使用它们。

**解决方案**:
修改 `on_start_recognition` 方法，使用正确的变量：
```python
def on_start_recognition(self):
    if not self.ocr_processor:
        QMessageBox.critical(self, "错误", "OCR 处理器未初始化或加载失败。")
        return
    if not self.image_path or not os.path.exists(self.image_path):  # 使用image_path检查文件
        QMessageBox.warning(self, "无图像", "请先上传有效的图像文件。")
        return
    
    # 其他代码保持不变...
    
    try:
        # 直接使用已加载的OpenCV图像
        if self.cv_image is None:
            raise ValueError("无法使用已加载的图像")
            
        # 使用现有的cv_image而不是重新加载
        results = self._perform_ocr(self.cv_image)
        
        # 其余处理逻辑...
```

### 3. 识别内容显示可读性问题

**问题描述**:
主页面识别内容缺乏视觉上的区分，需要用框子框起来提高可读性。

**原因分析**:
查看 UI 相关代码，结果显示部分使用了简单的 QLabel，缺乏明显的视觉区分：
```python
self.label_text_result = QLabel("标牌文字: 等待识别...")
self.print_text_result = QLabel("喷码文字: 等待识别...")
self.comparison_result = QLabel("比对结果: 等待比对...")
```

虽然创建了一个 `results_groupbox`，但单个结果文本之间没有额外的视觉分隔。

**解决方案**:
1. 为每个结果标签应用边框和背景样式
2. 可以使用 CSS 样式或 QFrame 实现边框效果：

```python
# 方案一：使用样式表
result_style = """
QLabel {
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 8px;
    background-color: #f8f8f8;
    margin: 2px;
    font-size: 12pt;
}
"""
self.label_text_result.setStyleSheet(result_style)
self.print_text_result.setStyleSheet(result_style)
self.comparison_result.setStyleSheet(result_style)

# 方案二：使用QFrame替代QLabel
self.label_text_frame = QFrame()
self.label_text_frame.setFrameShape(QFrame.StyledPanel)
self.label_text_frame.setFrameShadow(QFrame.Raised)
label_layout = QVBoxLayout(self.label_text_frame)
self.label_text_result = QLabel("标牌文字: 等待识别...")
label_layout.addWidget(self.label_text_result)
```

3. 根据记忆中的UI/UX增强记录，应当保持与之前风格一致，使用HTML格式来增强文本显示

### 4. 识别记录无法保存

**问题描述**:
识别完成后，相关结果无法保存到历史记录数据库中。

**原因分析**:
1. 代码审查发现，在相机识别完成后，记录保存代码被注释掉了：
```python
# 保存记录到数据库 (可选)
# filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
# save_path = os.path.join('path_to_save_captures', filename)
# cv2.imwrite(save_path, self.cv_image)
# self.add_record(save_path, label_text, print_text, result_text)
```

2. 静态图片识别部分也有类似问题：
```python
# Add record to database
# self.add_record(self.current_image, label_text, print_text, comparison)
```

3. 查看 `database_manager.py` 发现数据库功能已实现，但缺少关联的 `add_record` 方法。

4. 缺少用于保存捕获图像的目录结构。

**解决方案**:
1. 实现 `add_record` 方法调用数据库管理器：
```python
def add_record(self, image_path, sign_text, print_text, result_text):
    """将识别结果保存到数据库"""
    try:
        # 从比对结果中提取相似度
        import re
        similarity = 0.0
        if "相似度:" in result_text:
            match = re.search(r'相似度: (\d+)%', result_text)
            if match:
                similarity = float(match.group(1)) / 100
        
        # 提取结果（通过/不通过）
        result = "通过" if "通过" in result_text else "不通过"
        
        # 调用数据库函数保存记录
        from src.utils.database_manager import add_history_record
        add_history_record(image_path, sign_text, print_text, similarity, result)
        logger.info(f"Record saved: {image_path}, {sign_text}, {print_text}, {similarity}, {result}")
        return True
    except Exception as e:
        logger.error(f"Failed to save record: {e}")
        return False
```

2. 创建图像保存目录：
```python
def _ensure_capture_dir(self):
    """确保捕获图像的保存目录存在"""
    capture_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'captures')
    os.makedirs(capture_dir, exist_ok=True)
    return capture_dir
```

3. 取消注释并更新保存记录代码：
```python
# 相机识别完成后
if label_text != "<未识别到标牌文字>" and print_text != "<未识别到喷码文字>":
    # 保存当前帧
    from datetime import datetime
    capture_dir = self._ensure_capture_dir()
    filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    save_path = os.path.join(capture_dir, filename)
    cv2.imwrite(save_path, self.cv_image)
    
    # 保存记录
    self.add_record(save_path, label_text, print_text, result_text)
```

## 优先级与修复计划

1. **高优先级**: 修复上传图片识别导致应用闪退的问题
   - 修改 `on_start_recognition` 方法，使用正确的变量和图像数据

2. **中优先级**: 改进识别内容显示，提高可读性
   - 为结果标签添加边框和背景样式
   - 保持与现有UI风格一致，使用HTML增强显示效果

3. **中优先级**: 修复识别记录保存功能
   - 实现 `add_record` 方法
   - 创建捕获图像保存目录
   - 取消注释并更新保存记录代码

4. **低优先级**: 优化文本区分策略
   - 修改为不预先区分标牌/喷码文字的方案
   - 添加用户选择界面元素
