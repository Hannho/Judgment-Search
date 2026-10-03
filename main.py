import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 載入資料庫初始化模組
from database import init_user_tables

# 載入所有路由 (我們下一步會建立這些檔案)
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)