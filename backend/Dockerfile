# ---- 前端构建 ----
FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- 后端 ----
FROM python:3.11-slim
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
COPY backend/src ./src
COPY backend/config ./config
COPY --from=fe /fe/dist /frontend/dist
CMD ["uv", "run", "python", "-m", "src.main"]
