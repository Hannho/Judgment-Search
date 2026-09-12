import os
import time
import pymysql
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

# 爬蟲相關套件
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# AI 相關套件
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

# 載入環境變數
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key

app = FastAPI()

# 設定 CORS，讓網頁前端可以順利呼叫 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 0. 資料庫連線設定 (Google Cloud SQL)
# ==========================================
DB_HOST = os.getenv("DB_HOST", "35.221.215.146")
DB_USER = os.getenv("DB_USER", "admin1")
DB_PASSWORD = os.getenv("DB_PASSWORD", "12345678")  # ⚠️ 請替換為您的密碼，亦可寫在 .env
DB_NAME = os.getenv("DB_NAME", "judgment")

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# ==========================================
# 1. 靜態檔案與資料庫資料 API
# ==========================================
@app.get("/")
def read_index():
    if os.path.exists("index_final.html"):
        return FileResponse("index_final.html")
    return {"message": "index_final.html not found"}

@app.get("/style.css")
def get_css():
    if os.path.exists("style.css"):
        return FileResponse("style.css")
    return {"message": "style.css not found"}

# 💡 從 Cloud SQL 資料庫讀取所有裁判書
@app.get("/api/judgments")
def get_judgments_from_db():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "SELECT id, year, case_type, case_no, date, title, content, pdf_url FROM judgments"
            cursor.execute(sql)
            results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"❌ 資料庫讀取失敗: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# ==========================================
# 2. 爬蟲 API 區塊 (/api/get_history)
# ==========================================
class JudgmentRequest(BaseModel):
    id: str
    year: str
    case_type: str
    case_no: str
    date: str

COURT_MAPPING = {
    "TPS": "最高法院", "TPA": "最高行政法院", "TPC": "懲戒法院", "CPC": "司法院憲法法庭",
    "TPH": "臺灣高等法院", "TCH": "臺灣高等法院臺中分院", "TNH": "臺灣高等法院臺南分院",
    "KSH": "臺灣高等法院高雄分院", "HLH": "臺灣高等法院花蓮分院", "KMH": "福建高等法院金門分院",
    "TPB": "臺北高等行政法院", "TCB": "臺中高等行政法院", "KSB": "高雄高等行政法院",
    "TPD": "臺灣臺北地方法院", "SLD": "臺灣士林地方法院", "PCD": "臺灣新北地方法院",
    "TYD": "臺灣桃園地方法院", "SCD": "臺灣新竹地方法院", "MLD": "臺灣苗栗地方法院",
    "TCD": "臺灣臺中地方法院", "CHD": "臺灣彰化地方法院", "NTD": "臺灣南投地方法院",
    "YLD": "臺灣雲林地方法院", "CYD": "臺灣嘉義地方法院", "TND": "臺灣臺南地方法院",
    "KSD": "臺灣高雄地方法院", "PTD": "臺灣屏東地方法院", "TTD": "臺灣臺東地方法院",
    "HLD": "臺灣花蓮地方法院", "ILD": "臺灣宜蘭地方法院", "KLD": "臺灣基隆地方法院",
    "PHD": "臺灣澎湖地方法院", "KMD": "福建金門地方法院", "LCD": "福建連江地方法院",
    "CLE": "臺灣桃園地方法院中壢簡易庭", "TYE": "臺灣桃園地方法院桃園簡易庭",
    "PCE": "臺灣新北地方法院板橋簡易庭", "STE": "臺灣新北地方法院三重簡易庭",
    "TPE": "臺灣臺北地方法院臺北簡易庭", "SLE": "臺灣士林地方法院士林簡易庭",
    "NIE": "臺灣士林地方法院內湖簡易庭", "ILE": "臺灣宜蘭地方法院宜蘭簡易庭",
    "LTE": "臺灣宜蘭地方法院羅東簡易庭", "KSE": "臺灣高雄地方法院高雄簡易庭",
    "FSE": "臺灣高雄地方法院鳳山簡易庭", "KSY": "臺灣高雄少年及家事法院", 
    "IPC": "智慧財產及商業法院"
}

@app.post("/api/get_history")
def get_history(req: JudgmentRequest):
    court_code = req.id.split(",")[0][:3]
    court_name = COURT_MAPPING.get(court_code, "未知法院")
    
    tw_year = str(int(req.date[:4]) - 1911)
    target_date_str = f"{tw_year}.{req.date[4:6]}.{req.date[6:8]}"
    
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-notifications')
    
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"

    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    else:
        service = Service(ChromeDriverManager().install())
        
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 10)
    history_results = []
    
    try:
        driver.get("https://judgment.judicial.gov.tw/FJUD/default.aspx")
        
        search_query = f"{court_name}{req.year}{req.case_type}{req.case_no}"
        search_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='可輸入法院名稱']")))
        search_input.clear()
        search_input.send_keys(search_query)
        search_input.send_keys(Keys.RETURN)

        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "iframe-data")))
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
        
        xpath_query = f"//tr[td[contains(text(), '{target_date_str}')]]//a"
        exact_match_link = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_query)))
        exact_match_link.click()
            
        history_links = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.panel-body ul li a[href*='data.aspx']")))
        for link in history_links:
            title = link.text.strip()
            url = link.get_attribute("href")
            if not url.startswith("http"):
                url = "https://judgment.judicial.gov.tw/FJUD/" + url
            history_results.append({"title": title, "url": url})
            
    except Exception as e:
        print(f"爬蟲發生錯誤: {e}")
    finally:
        driver.quit()
        
    return {"history": history_results}

# ==========================================
# 3. AI 問答 API 區塊 (/api/ask_multiple)
# ==========================================
class MultiQAQuery(BaseModel):
    judgments_content: list[str]
    question: str

@app.post("/api/ask_multiple")
def ask_ai_multiple(query: MultiQAQuery):
    if not query.judgments_content:
        return {"answer": "目前沒有任何案件資料可供閱讀。"}

    texts_to_read = query.judgments_content[:50]
    context = "\n\n---\n\n".join(texts_to_read)
    
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "你是一位專業的法律助理。請綜合以下提供的 [篩選後裁判書內容] 來回答問題。\n"
                   "回答時，請務必明確指出是依據哪一個案號的判決。\n"
                   "如果你不知道答案，請直接說不知道，不要編造資訊。\n\n"
                   "[篩選後裁判書內容]：\n{context}"),
        ("human", "{input}")
    ])
    
    chain = prompt_template | llm
    
    try:
        response = chain.invoke({
            "context": context,
            "input": query.question
        })
        return {"answer": response.content}
    except Exception as e:
        print(f"AI 處理發生錯誤: {e}")
        return {"answer": f"AI 伺服器處理失敗，請確認 API Key 是否設定正確。錯誤詳情：{str(e)}"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)