# 环境与启动

## 一键启动（推荐）
- 双击 `start_with_conda.bat`，脚本会在已配置好的 conda 环境下启动应用

## 手动方式（如需）
1. 创建并激活环境（Python 3.8）：
   - conda create -y -n checkcheck python=3.8
   - conda activate checkcheck
2. 安装依赖：
   - pip install -r requirements.txt
3. 启动：
   - python src/main.py

## 离线交付（conda-pack）
1. 在联网开发机：
   - conda install -y -c conda-forge conda-pack
   - conda pack -n checkcheck -o checkcheck_env.tar.gz
2. 复制到离线电脑并解压到应用目录内（或同级）
3. 使用提供的 `start_with_conda.bat` 启动（脚本会优先使用已解压的环境）
