import os
import time          # 新增：用於計算處理速度
import traceback     # 新增：用於擷取詳細的錯誤訊息
import uvicorn

from fastapi import FastAPI, Request  # 新增：引入 Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse  # 新增：引入 JSONResponse
from fastapi.staticfiles import StaticFiles

# 載入資料庫初始化模組
from database import init_user_tables, log_api_usage

# 載入所有路由 (你的拆分檔案)
from routers import judgments, users, highlights, scraper, ai

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    try:
        init_user_tables()
        print("✅ 資料表初始化成功")
    except Exception as e:
        print(f"⚠️ 建立資料表失敗：{e}")

# 註冊 API 路由分流
app.include_router(judgments.router, prefix="/api/judgments", tags=["Judgments"])
app.include_router(users.router, prefix="/api", tags=["Users & Favorites"])
app.include_router(highlights.router, prefix="/api/highlights", tags=["Highlights"])
app.include_router(scraper.router, prefix="/api", tags=["Scraper"])
app.include_router(ai.router, prefix="/api", tags=["AI"])

# 將前端靜態檔案目錄對應到 /static (需新建 static 資料夾)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 根目錄首頁導向
@app.get("/")
def read_index():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "HTML template not found"}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("static/favicon.png")

# 👇 效能與錯誤日誌紀錄中介層
@app.middleware("http")
async def metrics_logging_middleware(request: Request, call_next):
    start_time = time.time()
    error_msg = ""
    status_code = 500
    
    # 嘗試從 Header 或 Token 中獲取 user_id (假設未登入為 None)
    user_id = None 

    try:
        # 讓系統繼續處理這個 API 請求
        response = await call_next(request)
        status_code = response.status_code
        return response

    except Exception as e:
        # 捕捉系統崩潰或任何未處理的錯誤訊息
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"🔥 [錯誤捕捉] {error_msg}") # 也可以同時印在終端機方便開發觀看
        return JSONResponse(status_code=500, content={"detail": "系統內部錯誤"})

    finally:
        # 計算處理速度 (秒)
        process_time = time.time() - start_time
        
        # 為了避免靜態檔案(CSS/JS)塞爆日誌，通常我們會過濾掉 /static 或 /favicon
        if not request.url.path.startswith("/static") and request.url.path != "/favicon.ico":
            try:
                # 將數據寫入 PostgreSQL
                log_api_usage(
                    user_id=user_id,
                    endpoint=request.url.path,
                    method=request.method,
                    process_time=process_time,
                    status_code=status_code,
                    error_message=error_msg
                )
            except Exception as db_err:
                print(f"⚠️ 寫入日誌到資料庫失敗: {db_err}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)