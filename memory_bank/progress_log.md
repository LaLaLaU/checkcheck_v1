# CheckCheck V1 项目进展日志

## 2025-05-04
- 引入 `src/core/text_comparator.py`，实现忽略空格和英文句点的文本比对逻辑。
- 修改 `src/ui/main_window.py` 中的 `_perform_camera_recognition` 和 `on_start_recognition` 方法，使其调用 `TextComparator` 进行比对，并从返回的字典中正确提取 `similarity` 值。
- 解决了此前因返回值类型不匹配导致的 `TypeError`。
- 确认比对功能现在可以正常工作，并按预期忽略空格/句点。
- 控制台调试日志验证了过滤和比对逻辑的正确执行。
- Implemented pass/fail sound effects on recognition result.
- Refined text comparison logic in `src/core/text_comparator.py` to ignore all non-alphanumeric characters using regex, improving comparison accuracy.

## 2025-08-31
- 重大方向调整：移除“标牌 vs 喷码”比对，转为“仅识别图号并自动复制”；架次号提供手动复制
- UI 重构：
  - 移除上传图像/切换到图片/设置
  - 结果区左右留白；新增右侧识别结果图预览
  - 相机画面完整显示，等比例不拉伸
  - 状态颜色：绿（严格）、黄（兜底）、红（无效）
  - 绑定 Enter/中键触发识别
- 识别规则：MAIN 严格/兜底；HEAD 正则；清洗规则（大写、去空格、去尾点、限定字符集）
- 声音：首次播放预热修复
- 历史记录：支持多选删除；新增“删记录+文件”
