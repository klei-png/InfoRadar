FROM docker.m.daocloud.io/library/python:3.11-slim

WORKDIR /app

# 先只拷贝依赖清单，利用 Docker 层缓存：代码改动不会触发重装依赖
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

COPY . .

CMD ["uv", "run", "python", "-m", "src.main"]
