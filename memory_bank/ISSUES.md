# CheckCheck 项目当前问题记录

**日期**: 2025-04-28
**版本**: 1.2

## 已解决问题

### 1. 上传图片识别导致应用闪退 

**问题描述**: 
上传图片后点击识别按钮会导致应用程序崩溃。

**解决方案**:
修改了 `on_start_recognition` 方法，使用正确的变量：
- 使用 `self.image_path` 而非 `self.current_image` 检查文件存在
- 使用已加载的 `self.cv_image` 进行OCR处理，而不是尝试重新加载图像

**实施状态**: 已解决

### 2. 识别记录无法保存 

**问题描述**:
识别完成后，相关结果无法保存到历史记录数据库中。

**解决方案**:
1. 实现了 `add_record` 方法调用数据库管理器
2. 创建了 `_ensure_capture_dir` 方法确保捕获图像的保存目录存在
3. 在静态图片和相机模式下都添加了记录保存代码

**实施状态**: 已解决

## 待解决问题

### 1. 文本区分策略不合理

**问题描述**: 
当前代码简单地根据文本框Y坐标位置区分上下文本（标牌/喷码），这种方法不够灵活，无法适应不同图像布局，特别是标牌竖放时完全无法区分。

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

**实施状态**: 待解决

### 2. 识别内容显示可读性问题

**问题描述**:
主页面识别内容虽然已添加基本样式，但仍缺乏足够的视觉区分，需要进一步提高可读性。

**原因分析**:
当前添加的样式可能不够明显：
```python
self.result_style = """
QLabel {
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 8px;
    background-color: #f8f8f8;
    margin: 2px;
    font-size: 12pt;
}
"""
```

**解决方案**:
1. 增强边框和背景对比度
2. 为不同类型的结果添加不同的视觉样式
3. 考虑使用QFrame嵌套或更明显的分隔线
4. 示例改进样式：
```python
self.label_text_style = """
QLabel {
    border: 2px solid #4a86e8;
    border-radius: 6px;
    padding: 10px;
    background-color: #e6f0ff;
    margin: 4px;
    font-size: 13pt;
    font-weight: bold;
}
"""

self.print_text_style = """
QLabel {
    border: 2px solid #6aa84f;
    border-radius: 6px;
    padding: 10px;
    background-color: #e6ffe6;
    margin: 4px;
    font-size: 13pt;
    font-weight: bold;
}
"""

self.comparison_style = """
QLabel {
    border: 2px solid #cc0000;
    border-radius: 6px;
    padding: 10px;
    background-color: #fff0f0;
    margin: 4px;
    font-size: 13pt;
    font-weight: bold;
}
"""
```

**实施状态**: 待解决

## 优先级与修复计划

1. **高优先级**: 优化文本区分策略
   - 修改为不预先区分标牌/喷码文字的方案
   - 添加用户选择界面元素
   - 重构相关比对逻辑

2. **中优先级**: 进一步改进识别内容显示，提高可读性
   - 为不同类型的结果添加更明显的视觉区分
   - 考虑使用QFrame替代QLabel或添加更明显的分隔
