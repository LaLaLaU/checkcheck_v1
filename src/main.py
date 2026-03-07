#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CheckCheck 导管喷码自动核对系统 - 主程序入口

此模块作为应用程序的入口点，负责初始化系统并启动主界面。
"""

import sys
import os
from PyQt5.QtWidgets import QApplication
import logging

# 确保可以导入其他模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入主窗口
from src.ui.main_window import MainWindow

def main():
    """
    应用程序主入口函数
    """
    # 创建QApplication实例
    app = QApplication(sys.argv)
    
    # 配置日志记录
    logging.basicConfig(level=logging.DEBUG, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        handlers=[
                            logging.StreamHandler(sys.stdout) 
                            # 可以添加 FileHandler 输出到文件
                            # logging.FileHandler("app.log") 
                        ])

    logger = logging.getLogger(__name__)
    logger.info("Application starting...") 

    # 设置应用程序信息
    app.setApplicationName("CheckCheck")
    app.setOrganizationName("CheckCheck")
    app.setOrganizationDomain("checkcheck.example.com")
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    # 进入应用程序主循环
    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"程序启动错误: {e}")
        import traceback
        traceback.print_exc()
