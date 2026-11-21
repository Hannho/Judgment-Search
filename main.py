import os
import time
import traceback
import asyncio
import uvicorn

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# 載入資料庫初始化模組
from database import init_user_tables, log_api_usage

# 載入夜間自動排程器
from services.scheduler import start_nightly_scheduler

# 載入所有路由
from routers import judgments, users, highlights, scraper, ai, sync

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    try:
        init_user_tables()
        print("[startup] 資料表初始化成功")
    except Exception as e:
        print(f"[startup] 建立資料表失敗：{e}")

    try:
        start_nightly_scheduler()
    except Exception as e:
        print(f"[startup] 啟動夜間自動排程器失敗：{e}")

# 註冊 API 路由分流
app.include_router(judgments.router, prefix="/api/judgments", tags=["Judgments"])
app.include_router(users.router, prefix="/api", tags=["Users & Favorites"])
app.include_router(highlights.router, prefix="/api/highlights", tags=["Highlights"])
app.include_router(scraper.router, prefix="/api/scraper", tags=["Scraper"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(sync.router, prefix="/api/sync", tags=["Sync"])

# 兼容舊版與無前綴別名 (確保無論前端是否帶有子模組前綴皆能正常存取)
app.add_api_route("/api/get_history", scraper.get_history, methods=["POST"], tags=["Scraper"])
app.add_api_route("/api/get_judgment", scraper.get_judgment, methods=["POST"], tags=["Scraper"])
app.add_api_route("/api/ask_multiple", ai.ask_ai_multiple, methods=["POST"], tags=["AI"])
app.add_api_route("/api/ask_stream", ai.ask_ai_stream, methods=["POST"], tags=["AI"])
app.add_api_route("/api/judge_analytics", judgments.get_judge_analytics, methods=["POST"], tags=["Judgments"])
app.add_api_route("/api/compensation_analytics", judgments.get_compensation_analytics, methods=["POST"], tags=["Judgments"])
app.add_api_route("/api/case_brief", ai.generate_case_brief, methods=["POST"], tags=["AI"])
app.add_api_route("/api/compare_diff", ai.compare_judgments_diff, methods=["POST"], tags=["AI"])

# 將前端靜態檔案目錄對應到 /static
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

# 效能與錯誤日誌紀錄中介層
@app.middleware("http")
async def metrics_logging_middleware(request: Request, call_next):
    start_time = time.time()
    error_msg = ""
    status_code = 500
    
    # 嘗試從 Header 中獲取 user_id (未登入為 None)
    raw_uid = request.headers.get("x-user-id")
    user_id = int(raw_uid) if raw_uid and raw_uid.isdigit() else None

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response

    except Exception as e:
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"[error] 錯誤捕捉: {error_msg}")
        return JSONResponse(status_code=500, content={"detail": "系統內部錯誤"})

    finally:
        process_time = time.time() - start_time
        
        # 過濾靜態檔案以防塞爆日誌
        if not request.url.path.startswith("/static") and request.url.path != "/favicon.ico":
            try:
                # 使用 asyncio.to_thread 避免同步 DB 查詢阻塞 Event Loop
                await asyncio.to_thread(
                    log_api_usage,
                    user_id=user_id,
                    endpoint=request.url.path,
                    method=request.method,
                    process_time=process_time,
                    status_code=status_code,
                    error_message=error_msg
                )
            except Exception as db_err:
                print(f"[log] 寫入日誌到資料庫失敗: {db_err}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8088))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
