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
主页面识别内容缺乏视觉区分，需要在图像上直接标记识别到的文字区域。在相机模式下，识别后主界面仍显示实时相机画面，无法看到标记的文本框。

**解决方案**:
1. 添加了 `_draw_text_boxes` 方法，用于在图像上绘制文本框和标签
2. 在相机模式和静态图片模式下的识别过程中，都添加了绘制文本框的代码
3. 使用不同颜色区分不同类型的文本（绿色表示标牌文字，红色表示喷码文字）
4. 移除了文本标签中的序号前缀，只显示文本内容和置信度
5. 添加了暂停相机画面更新的功能，确保在识别完成后显示带有文本框标记的抓取画面
6. 重构了相机识别过程，使用QTimer延时确保获取最新画面
7. 添加了"恢复相机"按钮，允许用户在查看识别结果后恢复实时相机画面，方便调整画面内容

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
        label = f"{text} ({confidence:.2f})"
        min_x = min(point[0] for point in box)
        min_y = min(point[1] for point in box)
        cv2.putText(marked_image, label, (int(min_x), int(min_y) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    return marked_image

# 添加暂停标志
self.pause_camera_updates = False

# 修改update_frame方法，在暂停状态下不更新画面
def update_frame(self, frame: np.ndarray):
    if not self.camera_running:
        return
        
    # 如果暂停相机画面更新，则不更新画面
    if self.pause_camera_updates:
        return
        
    # 保存当前帧并更新显示
    self.cv_image = frame.copy()
    # ...

# 在识别完成后暂停相机画面更新
self.pause_camera_updates = True

# 在_recognize_current_frame方法中重置暂停状态
def _recognize_current_frame(self):
    # ...
    if self.camera_running and self.cv_image is not None:
        # 重置暂停状态，确保获取最新的相机画面
        self.pause_camera_updates = False
        # 短暂延时，确保获取到最新的画面
        QTimer.singleShot(100, self._perform_camera_recognition)

# 添加恢复相机按钮
self.resume_camera_button = QPushButton(" 恢复相机")
self.resume_camera_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
self.resume_camera_button.setEnabled(False)  # 初始状态下禁用
self.resume_camera_button.clicked.connect(self.resume_camera)
button_layout.addWidget(self.resume_camera_button)

# 在识别完成后暂停相机画面更新并启用恢复按钮
self.pause_camera_updates = True
self.resume_camera_button.setEnabled(True)

# 恢复相机实时画面的方法
def resume_camera(self):
    """恢复相机实时画面"""
    self.pause_camera_updates = False
    self.resume_camera_button.setEnabled(False)

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

### 5. 图片识别和相机识别模式切换功能

**问题描述**: 
当前应用程序无法在图片识别和相机识别模式之间切换。

**原因分析**:
缺少实现模式切换的代码。

**解决方案**:
1. 添加模式切换按钮
2. 实现模式切换逻辑
3. 在相机模式下添加暂停相机画面更新的功能

具体实现：
```python
# 添加模式切换按钮
self.mode_switch_button = QPushButton(" 切换模式")
self.mode_switch_button.clicked.connect(self.switch_mode)
button_layout.addWidget(self.mode_switch_button)

# 实现模式切换逻辑
def switch_mode(self):
    if self.current_mode == "图片识别":
        self.current_mode = "相机识别"
        # 启动相机
        self.start_camera()
    else:
        self.current_mode = "图片识别"
        # 停止相机
        self.stop_camera()

# 在相机模式下添加暂停相机画面更新的功能
def update_frame(self, frame: np.ndarray):
    if not self.camera_running:
        return
        
    # 如果暂停相机画面更新，则不更新画面
    if self.pause_camera_updates:
        return
        
    # 保存当前帧并更新显示
    self.cv_image = frame.copy()
    # ...
```

**实施状态**: 已解决

### 6. 上传图像识别后切换为相机导致应用闪退

**问题描述**: 
上传图像识别后切换为相机模式导致应用闪退。

**原因分析**:
在 `switch_to_camera_mode` 方法中先停止相机再启动相机，但在上传图像识别后相机并未启动，导致 `stop_camera` 方法出错。

**解决方案**:
1. 修改 `switch_to_camera_mode` 方法，先检查相机是否已经启动
2. 移除不必要的 `stop_camera` 调用
3. 在启动相机前清除当前图像显示并重置相关变量

## 待解决问题

### 文本区分策略问题
- **问题描述**: 当前基于Y坐标区分标牌文字和喷码文字的策略不可靠，特别是当标牌竖放时完全失效
- **原因**: 简单地假设Y坐标较小的是标牌文字，Y坐标较大的是喷码文字
- **解决方案**: 
  - 修改应用程序，允许用户手动选择标牌文字和喷码文字
  - 添加UI元素（如下拉列表）供用户选择
  - 重构比对逻辑，使用用户选择的文本

## 优先级与修复计划

1. **高优先级**: 优化文本区分策略
   - 修改为不预先区分标牌/喷码文字的方案
   - 添加用户选择界面元素
   - 重构相关比对逻辑

2. **中优先级**: 进一步改进识别内容显示，提高可读性
   - 为不同类型的结果添加更明显的视觉区分
   - 考虑使用QFrame替代QLabel或添加更明显的分隔
