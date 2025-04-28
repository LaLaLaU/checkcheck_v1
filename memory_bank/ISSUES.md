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

### 3. 识别内容显示可读性问题 

**问题描述**:
主页面识别内容缺乏视觉区分，需要在图像上直接标记识别到的文字区域。

**解决方案**:
1. 添加了 `_draw_text_boxes` 方法，用于在图像上绘制文本框和标签
2. 在相机模式和静态图片模式下的识别过程中，都添加了绘制文本框的代码
3. 使用不同颜色区分不同类型的文本（绿色表示标牌文字，红色表示喷码文字）
4. 在每个文本框旁边显示文本内容和置信度

具体实现：
```python
def _draw_text_boxes(self, image, text_boxes):
    """在图像上绘制文本框"""
    if image is None or not text_boxes:
        return image
        
    # 创建图像副本，避免修改原图
    marked_image = image.copy()
    
    # 为不同类型的文本设置不同颜色
    colors = [
        (0, 255, 0),    # 绿色 - 标牌文字
        (0, 0, 255),    # 红色 - 喷码文字
        (255, 0, 0)     # 蓝色 - 其他文字
    ]
    
    # 绘制每个文本框
    for i, (box, text, confidence, _) in enumerate(text_boxes):
        # 确定颜色索引
        color_idx = i % len(colors) if i < 2 else 2
        color = colors[color_idx]
        
        # 绘制文本框
        points = np.array(box).astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(marked_image, [points], True, color, 2)
        
        # 添加文本标签
        label = f"{i+1}: {text} ({confidence:.2f})"
        min_x = min(point[0] for point in box)
        min_y = min(point[1] for point in box)
        cv2.putText(marked_image, label, (int(min_x), int(min_y) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    return marked_image
```

**实施状态**: 已解决

### 4. 文本区分策略不合理

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

## 优先级与修复计划

1. **高优先级**: 优化文本区分策略
   - 修改为不预先区分标牌/喷码文字的方案
   - 添加用户选择界面元素
   - 重构相关比对逻辑

2. **中优先级**: 进一步改进识别内容显示，提高可读性
   - 为不同类型的结果添加更明显的视觉区分
   - 考虑使用QFrame替代QLabel或添加更明显的分隔
