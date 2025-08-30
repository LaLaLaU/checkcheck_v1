离线交付包使用说明
================================
1) 将整个 delivery_offline 文件夹拷贝到目标机英文路径（如 D:\checkcheck）
2) 双击 start_app.bat 启动；首次会自动运行 conda-unpack 修复环境
3) 若提示缺少 VC++ 运行库，请先安装 VS 2015-2022 x64 运行库
4) 若无法打开摄像头，可先用图片识别验证；如为 Win10 N 版需安装 Media Feature Pack
5) 需 CPU 支持 AVX/AVX2；如过旧 CPU 可能无法运行
6) 目录需可写：data\\history.db 和 captures\\
7) 默认纯 CPU 推理，无需显卡与网络
