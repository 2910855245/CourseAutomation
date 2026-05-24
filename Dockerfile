# ---- Stage 1: 前端构建 ----
FROM node:18-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: 后端运行 ----
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-build /app/frontend/dist/ ./static/

RUN mkdir -p data uploads

EXPOSE 8000

CMD ["granian", \
     "--interface", "asgi", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--threads", "4", "--blocking-threads", "2", \
     "--loop", "uvloop", "--opt", \
     "--http", "2", \
     "--http2-adaptive-window", \
     "--http2-max-concurrent-streams", "200", \
     "--backlog", "2048", "--backpressure", "100", \
     "--respawn-failed-workers", "--respawn-interval", "3.5", \
     "--workers-lifetime", "3600", \
     "--log-level", "warning", "--access-log", \
     "--pid-file", "server.pid", \
     "--process-name", "anti_course", \
     "run:app"]
