# 使用官方輕量版 Python 映像檔
FROM python:3.9-slim

# 設定工作目錄
WORKDIR /app

# 複製並安裝 Python 套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製所有專案檔案到容器中
COPY . .

# 讓 Cloud Run 能夠正確監聽環境變數指定的 Port
ENV PORT=8080

# 啟動 FastAPI
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}