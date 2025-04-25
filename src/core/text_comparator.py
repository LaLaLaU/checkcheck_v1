#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - 文本比对模块

此模块负责比对标牌文字和喷码文字，计算相似度并标记不同之处。
"""

import difflib
from typing import Dict, List, Tuple


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
            Dict: 比对结果，包括：
                - similarity: 相似度（0-1之间的浮点数）
                - is_match: 是否匹配（布尔值）
                - diff_details: 差异详情
        """
        # 处理空文本情况
        if not text1 or not text2:
            return {
                'similarity': 0.0,
                'is_match': False,
                'diff_details': []
            }
        
        # 计算相似度
        similarity = self._calculate_similarity(text1, text2)
        
        # 获取差异详情
        diff_details = self._get_diff_details(text1, text2)
        
        # 判断是否匹配
        is_match = similarity >= self.similarity_threshold
        
        return {
            'similarity': similarity,
            'is_match': is_match,
            'diff_details': diff_details
        }
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两段文本的相似度
        
        Args:
            text1 (str): 第一段文本
            text2 (str): 第二段文本
            
        Returns:
            float: 相似度（0-1之间的浮点数）
        """
        # 使用SequenceMatcher计算相似度
        matcher = difflib.SequenceMatcher(None, text1, text2)
        return matcher.ratio()
    
    def _get_diff_details(self, text1: str, text2: str) -> List[Dict]:
        """
        获取两段文本的差异详情
        
        Args:
            text1 (str): 第一段文本
            text2 (str): 第二段文本
            
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
        # 使用SequenceMatcher获取差异
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
                html1 += f'<span style="background-color: #ffcccc;">{diff["text1_value"]}</span>'
                html2 += f'<span style="background-color: #ccffcc;">{diff["text2_value"]}</span>'
            elif diff['type'] == 'delete':
                html1 += f'<span style="background-color: #ffcccc;">{diff["text1_value"]}</span>'
            elif diff['type'] == 'insert':
                html2 += f'<span style="background-color: #ccffcc;">{diff["text2_value"]}</span>'
        
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
