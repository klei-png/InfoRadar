# ---- 前端构建 ----
# node 版本需与生成 package-lock.json 的本地 Node 对齐（本地 Node 24 / npm 11）
FROM docker.m.daocloud.io/library/node:24-alpine AS fe
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
# 用 npm install 而非 npm ci：lock 在 Windows 生成，缺 alpine(musl) 平台的
# rolldown wasm 回退依赖（@emnapi/*），npm ci 的严格校验会误报 Missing。
RUN npm config set registry https://registry.npmmirror.com && npm install
COPY frontend/ .
RUN npm run build

# ---- 后端 ----
FROM docker.m.daocloud.io/library/python:3.11-slim
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv && \
    uv sync --frozen --no-dev --default-index https://pypi.tuna.tsinghua.edu.cn/simple
COPY backend/src ./src
COPY backend/config ./config
COPY --from=fe /fe/dist /frontend/dist
CMD ["uv", "run", "python", "-m", "src.main"]
