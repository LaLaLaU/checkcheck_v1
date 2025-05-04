#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - 文本比对模块

此模块负责比对标牌文字和喷码文字，计算相似度并标记不同之处。
"""

import difflib
from typing import Dict, List, Tuple
import logging
import re # 导入 re 模块

logger = logging.getLogger(__name__)

class TextComparator:
    """
    文本比对类，用于比较两段文本的相似度
    """
    
    def __init__(self):
        """
        初始化文本比对器
        """
        # 配置参数
        self.similarity_threshold = 0.8  # 相似度阈值，高于此值视为通过
        
    def compare_texts(self, text1: str, text2: str) -> Dict:
        """
        比较两段文本的相似度
        
        Args:
            text1 (str): 第一段文本（通常是标牌文字）
            text2 (str): 第二段文本（通常是喷码文字）
            
        Returns:
            Dict: 包含相似度和差异详情的字典
                - similarity (float): 0-1之间的相似度 (忽略空格计算)
                - diff_details (List[Dict]): 差异详情列表 (基于原始文本)
                - highlighted_text1 (str): 高亮显示差异的第一段文本 (基于原始文本)
                - highlighted_text2 (str): 高亮显示差异的第二段文本 (基于原始文本)
        """
        # 处理空文本情况
        if not text1 or not text2:
            return {
                'similarity': 0.0,
                'is_match': False,
                'diff_details': [],
                'highlighted_text1': '',
                'highlighted_text2': ''
            }
        
        # 计算相似度
        similarity = self._calculate_similarity(text1, text2)
        
        # 获取差异详情
        diff_details = self._get_diff_details(text1, text2)
        
        # 高亮显示差异
        highlighted_text1, highlighted_text2 = self._highlight_diffs(text1, text2, diff_details)
        
        # 判断是否匹配
        is_match = similarity >= self.similarity_threshold
        
        return {
            'similarity': similarity,
            'is_match': is_match,
            'diff_details': diff_details,
            'highlighted_text1': highlighted_text1,
            'highlighted_text2': highlighted_text2
        }
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两段文本的相似度 (忽略空格和英文句点)

        Args:
            text1 (str): 第一段文本
            text2 (str): 第二段文本

        Returns:
            float: 相似度（0-1之间的浮点数）
        """
        # 过滤文本：只保留字母和数字
        text1_filtered = re.sub(r'[^a-zA-Z0-9]', '', text1)
        text2_filtered = re.sub(r'[^a-zA-Z0-9]', '', text2)

        # 添加调试日志
        logger.debug(f"Comparing filtered texts:")
        logger.debug(f"  Text1 Filtered: '{text1_filtered}'")
        logger.debug(f"  Text2 Filtered: '{text2_filtered}'")

        # 处理空字符串或仅包含空格和句点的情况
        if not text1_filtered and not text2_filtered:
            return 1.0  # 两者都为空（或只有空格和句点），视为相同
        if not text1_filtered or not text2_filtered:
             # 其中一个为空（移除空格和句点后），另一个不为空
             # 如果要求严格匹配，则返回0.0。如果认为空匹配空，则需要更复杂的逻辑。
             # 当前场景下，一个有字符一个没字符，相似度应为0。
            return 0.0

        # 使用SequenceMatcher计算相似度
        matcher = difflib.SequenceMatcher(None, text1_filtered, text2_filtered)
        similarity_ratio = matcher.ratio() # 获取比率
        logger.debug(f"Similarity Ratio: {similarity_ratio}") # 添加调试日志

        return similarity_ratio
    
    def _get_diff_details(self, text1: str, text2: str) -> List[Dict]:
        """
        获取两段文本的差异详情 (基于原始文本)

        Args:
            text1 (str): 第一段文本 (原始)
            text2 (str): 第二段文本 (原始)

        Returns:
            List[Dict]: 差异详情列表，每项包含：
                - type: 差异类型（'equal', 'replace', 'delete', 'insert'）
                - text1_start: 第一段文本中的起始位置
                - text1_end: 第一段文本中的结束位置
                - text1_value: 第一段文本中的值
                - text2_start: 第二段文本中的起始位置
                - text2_end: 第二段文本中的结束位置
                - text2_value: 第二段文本中的值
        """
        # 使用SequenceMatcher获取差异 (基于原始文本)
        matcher = difflib.SequenceMatcher(None, text1, text2)
        opcodes = matcher.get_opcodes()
        
        diff_details = []
        for tag, i1, i2, j1, j2 in opcodes:
            diff_details.append({
                'type': tag,
                'text1_start': i1,
                'text1_end': i2,
                'text1_value': text1[i1:i2],
                'text2_start': j1,
                'text2_end': j2,
                'text2_value': text2[j1:j2]
            })
        
        return diff_details
    
    def _highlight_diffs(self, text1: str, text2: str, diff_details: List[Dict]) -> Tuple[str, str]:
        """
        高亮显示差异

        Args:
            text1 (str): 第一段文本
            text2 (str): 第二段文本
            diff_details (List[Dict]): 差异详情列表

        Returns:
            Tuple[str, str]: 高亮显示差异的第一段文本和第二段文本
        """
        highlighted_text1 = ""
        highlighted_text2 = ""
        
        for diff in diff_details:
            if diff['type'] == 'equal':
                highlighted_text1 += diff['text1_value']
                highlighted_text2 += diff['text2_value']
            elif diff['type'] == 'replace':
                highlighted_text1 += f'<b><font color="red">{diff["text1_value"]}</font></b>'
                highlighted_text2 += f'<b><font color="green">{diff["text2_value"]}</font></b>'
            elif diff['type'] == 'delete':
                highlighted_text1 += f'<b><font color="red">{diff["text1_value"]}</font></b>'
            elif diff['type'] == 'insert':
                highlighted_text2 += f'<b><font color="green">{diff["text2_value"]}</font></b>'
        
        return highlighted_text1, highlighted_text2
    
    def format_diff_html(self, text1: str, text2: str) -> Tuple[str, str]:
        """
        生成HTML格式的差异显示
        
        Args:
            text1 (str): 第一段文本
            text2 (str): 第二段文本
            
        Returns:
            Tuple[str, str]: 包含HTML标记的两段文本
        """
        # 获取差异详情
        diff_details = self._get_diff_details(text1, text2)
        
        # 生成HTML
        html1 = ""
        html2 = ""
        
        for diff in diff_details:
            if diff['type'] == 'equal':
                html1 += diff['text1_value']
                html2 += diff['text2_value']
            elif diff['type'] == 'replace':
                html1 += f'<b><font color="red">{diff["text1_value"]}</font></b>'
                html2 += f'<b><font color="green">{diff["text2_value"]}</font></b>'
            elif diff['type'] == 'delete':
                html1 += f'<b><font color="red">{diff["text1_value"]}</font></b>'
            elif diff['type'] == 'insert':
                html2 += f'<b><font color="green">{diff["text2_value"]}</font></b>'
        
        return html1, html2
    
    def set_similarity_threshold(self, threshold: float) -> None:
        """
        设置相似度阈值
        
        Args:
            threshold (float): 新的相似度阈值，范围为0到1
        """
        if 0 <= threshold <= 1:
            self.similarity_threshold = threshold
    
    def get_similarity_threshold(self) -> float:
        """
        获取当前相似度阈值
        
        Returns:
            float: 当前相似度阈值
        """
        return self.similarity_threshold
