离线包使用说明（UTF-8）
================================
1) 将整个 `delivery_offline` 文件夹放到纯英文路径（例如 `D:\checkcheck`）。
2) 首次运行：双击 `start_app.bat`，脚本会自动执行 `env\Scripts\conda-unpack.exe` 完成环境修复，然后启动应用。
3) 若提示缺少 VC++ 运行库，请安装 “Microsoft Visual C++ 2015-2022 Redistributable (x64)”。
4) 若系统为 Win10 N 且无法使用多媒体功能，请安装 “Media Feature Pack”。
5) 建议 CPU 支持 AVX/AVX2；过旧 CPU 可能无法运行。
6) 程序运行后，会在同目录生成：
   - `data\history.db`（识别历史）与 `captures\`（标注截图）。
   - `data\config.json`（应用设置）与 `data\char_index.json`（字符文件索引）。
7) 默认使用 CPU 运行；如需 GPU 请自行配置对应的 Paddle 版本与驱动。
8) 本包已内置自动化依赖（pywinauto/pywin32/comtypes/six）。演示脚本位于 `tools\demo_vendor_automation.py`。

【首次配置】
1) 启动应用后，点击底部“设置”。
2) 在“字符文件路径”选择生产机字符文件根目录，点击“重建字符文件索引”。
3) 如需自动启动喷码软件，可在“喷码软件 exe(可选)”中选择其可执行文件；否则请先手动打开喷码软件。
4) 识别出图号后，界面会显示“字符文件: … (score=…)”；点击“打开字符文件”联动喷码软件。

【自动化演示（可选）】
1) 以管理员身份运行 `start_demo.bat`，或手动执行：
   `env\python.exe tools\demo_vendor_automation.py --exe "D:\\Vendor\\App\\VendorApp.exe"`
2) 如窗口标题不匹配，可加 `--title-re "你的窗口标题关键字"`。
