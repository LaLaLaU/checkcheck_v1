# CheckCheck 环境设置步骤

由于在批处理文件中执行conda命令时遇到一些问题，请按照以下步骤手动设置环境：

## 1. 配置conda使用清华镜像

打开命令提示符或PowerShell，执行以下命令：

```bash
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/
conda config --set show_channel_urls yes
conda config --set ssl_verify false
conda config --remove channels defaults
```

## 2. 创建Python 3.8环境

```bash
conda create -y -n checkcheck python=3.8
```

## 3. 激活环境并安装依赖

```bash
conda activate checkcheck
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

## 4. 启动应用程序

```bash
conda activate checkcheck
python src/main.py
```

## 5. 打包环境（可选，用于离线部署）

```bash
conda activate checkcheck
conda install -y -c conda-forge conda-pack
conda pack -n checkcheck -o checkcheck_env.tar.gz
```

按照上述步骤操作，应该能够成功创建环境并安装依赖。
