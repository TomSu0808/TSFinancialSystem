# ---------- 阶段一：构建前端 ----------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
# 先拷依赖清单，利用 Docker 层缓存：依赖没变就不重装
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build      # 产出 /app/frontend/dist

# ---------- 阶段二：后端运行时 ----------
FROM python:3.12-slim
WORKDIR /app/backend

# 少量系统依赖：个别 Python 包（如 jsonpath 从源码构建）需要编译工具
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 先装 Python 依赖（同样利用层缓存）
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# 多 Agent 引擎装在独立 venv：它要求 pandas 3，不能与后端的 pandas 2 混装。
ARG INSTALL_TRADINGAGENTS=1
COPY backend/requirements-tradingagents.txt ./
RUN if [ "$INSTALL_TRADINGAGENTS" = "1" ]; then \
        python -m venv /opt/tradingagents-venv \
        && /opt/tradingagents-venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
        && /opt/tradingagents-venv/bin/pip install --no-cache-dir -r requirements-tradingagents.txt; \
    fi

# 拷后端源码
COPY backend/ ./
# 把阶段一构建好的前端产物放到 FastAPI 期望的位置（frontend/dist）
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# UTF-8 输出；DATA_DIR 指向挂载卷，让 SQLite 数据持久化（见 fly.toml 的 mounts）
ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    DATA_DIR=/data \
    TRADINGAGENTS_PYTHON=/opt/tradingagents-venv/bin/python \
    TRADINGAGENTS_DATA_ROOT=/data/tradingagents

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
