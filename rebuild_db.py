"""
一个简单的脚本，用于重建数据库表，确保表结构是最新的。
运行此脚本将删除现有的历史记录表并创建一个新的空表。
"""
import logging
import sys
import os

# 设置日志级别
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 确保能找到项目模块
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 导入数据库管理模块
from src.utils.database_manager import init_db

def main():
    """重建数据库表"""
    logging.info("开始重建数据库表...")
    
    try:
        # 调用init_db函数并传入rebuild=True参数，强制重建表
        init_db(rebuild=True)
        logging.info("数据库表重建成功！")
        print("数据库表重建成功！现在可以重新启动应用程序了。")
    except Exception as e:
        logging.error(f"重建数据库表失败: {e}", exc_info=True)
        print(f"错误: 重建数据库表失败: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
