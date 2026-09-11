FROM python:3.10-slim

WORKDIR /app

# 安裝 Chromium 瀏覽器與驅動相關套件
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080

CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}