# backend/Dockerfile
# ---------------
# 基于 Python 3.11 slim 镜像，配置清华 pip 源加速安装依赖，
# 最终使用 uvicorn 启动 FastAPI 应用。

FROM python:3.11.9-slim

# 设置工作目录
WORKDIR /app

# 设置 HuggingFace 国内镜像，加速 docling 按需下载模型权重
ENV HF_ENDPOINT=https://hf-mirror.com

# 更换 Debian 源为国内清华镜像，并安装 docling / PyTorch 等依赖所需的系统库
# libgomp1: PyTorch 多线程需要
# libglib2.0-0: 部分图像处理库底层依赖
# gcc/g++: 极少数 Python 包编译 C 扩展时需要
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc g++ \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 先升级 pip 并配置国内镜像源，增加超时时间和重试次数
RUN pip install --upgrade pip \
    && pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip config set global.timeout 500 \
    && pip config set global.retries 15

# 【关键】先预装 CPU 版 PyTorch，避免 docling 拉取 2GB+ 的 CUDA 运行时包
# torch>=2.5 兼容最新 transformers（AutoModelForImageTextToText 需要）
RUN pip install 'torch>=2.5.0' 'torchvision>=0.20.0' --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .

# 分步安装：先装除 docling 外的大部分依赖（利用 Docker layer cache）
RUN grep -v '^docling' requirements.txt > /tmp/requirements_base.txt \
    && pip install -r /tmp/requirements_base.txt

# 单独安装最新版 transformers（AutoModelForImageTextToText 需要 >=4.48）和 accelerate
RUN pip install 'transformers>=4.51.0' accelerate

# 安装 docling
RUN pip install 'docling>=2.15.0'

# 复制后端全部代码，但排除 .env（防止覆盖容器环境变量）
COPY . .
RUN rm -f /app/.env

# 暴露 FastAPI 服务端口
EXPOSE 8000

# 使用 uvicorn 启动应用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
