# EEG-EmoStudio 工作台镜像
#
# 构建： docker build -t eeg-emostudio .
# 运行： docker run --rm -p 8770:8770 \
#          -v "%cd%/data:/data" -v "%cd%/artifacts:/artifacts" \
#          -e EEG_WEB_TOKEN=换成你自己的口令 eeg-emostudio
#
# 只打包代码与少量研究输入（质量排序 CSV），数据/产物/交付文档全部走挂载卷：
# 镜像保持在几百 MB，数据始终留在宿主机，重装容器不丢数据。

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    EEG_DATA_DIR=/data \
    EEG_ARTIFACTS_DIR=/artifacts \
    EEG_DELIVERABLES_DIR=/deliverables \
    EEG_WEB_HOST=0.0.0.0 \
    EEG_WEB_PORT=8770

WORKDIR /app

COPY requirements.txt ./
# torch 先单独装 CPU 版，避免把 2 GB 的 CUDA 轮子拉进镜像
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./
COPY run_web.py ./
COPY eeg_emostudio ./eeg_emostudio
COPY webapp ./webapp
# 素材库与工作台统计需要质量排序表，体量很小（KB 级）
COPY research/quality ./research/quality

RUN mkdir -p /data /artifacts /deliverables
VOLUME ["/data", "/artifacts", "/deliverables"]

EXPOSE 8770

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8770/api/health', timeout=2).status==200 else 1)"

CMD ["python", "-m", "webapp"]
