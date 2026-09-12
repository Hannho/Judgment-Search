# 使用官方輕量版 Python 映像檔
FROM python:3.9-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴（若有使用 Selenium 爬蟲，通常需要 Chromium 相關套件，若無爬蟲可拿掉）
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# 複製並安裝 Python 套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製所有專案檔案到容器中
COPY . .

# 讓 Cloud Run 能夠正確監聽環境變數指定的 Port
ENV PORT=8080

# 啟動 FastAPI (使用 uvicorn，並綁定 0.0.0.0:$PORT)
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}