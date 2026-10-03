import os
from fastapi import APIRouter
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

router = APIRouter()

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
    "CTD": "臺灣橋頭地方法院", "ULD": "臺灣雲林地方法院", 
    "TPE": "臺灣臺北地方法院臺北簡易庭", "SDE": "臺灣臺北地方法院新店簡易庭",
    "SLE": "臺灣士林地方法院士林簡易庭", "NIE": "臺灣士林地方法院內湖簡易庭", "NHE": "臺灣臺北地方法院內湖簡易庭",
    "PCE": "臺灣新北地方法院板橋簡易庭", "STE": "臺灣新北地方法院三重簡易庭",
    "KLE": "臺灣基隆地方法院基隆簡易庭", 
    "TYE": "臺灣桃園地方法院桃園簡易庭", "CLE": "臺灣桃園地方法院中壢簡易庭",
    "SJE": "臺灣新竹地方法院新竹簡易庭", "CDE": "臺灣新竹地方法院竹東簡易庭",
    "MLE": "臺灣苗栗地方法院苗栗簡易庭",
    "TCE": "臺灣臺中地方法院臺中簡易庭", "FYE": "臺灣臺中地方法院豐原簡易庭", "CSE": "臺灣臺中地方法院清水簡易庭", 
    "CHE": "臺灣彰化地方法院彰化簡易庭", "YLE": "臺灣彰化地方法院員林簡易庭", "PDE": "臺灣彰化地方法院北斗簡易庭", "OLE": "臺灣彰化地方法院員林簡易庭",
    "NTE": "臺灣南投地方法院南投簡易庭", "PLE": "臺灣南投地方法院埔里簡易庭",
    "ULE": "臺灣雲林地方法院雲林簡易庭", "TLE": "臺灣雲林地方法院斗六簡易庭", "HUE": "臺灣雲林地方法院虎尾簡易庭", "PKE": "臺灣雲林地方法院北港簡易庭",
    "CYE": "臺灣嘉義地方法院嘉義簡易庭", "PZE": "臺灣嘉義地方法院朴子簡易庭",
    "TNE": "臺灣臺南地方法院臺南簡易庭", "SYE": "臺灣臺南地方法院新營簡易庭", "SSE": "臺灣臺南地方法院新市簡易庭", "LYE": "臺灣臺南地方法院柳營簡易庭",
    "KSE": "臺灣高雄地方法院高雄簡易庭", "FSE": "臺灣高雄地方法院鳳山簡易庭", "GSE": "臺灣橋頭地方法院岡山簡易庭", "CCE": "臺灣橋頭地方法院橋頭簡易庭", "CTE": "臺灣橋頭地方法院橋頭簡易庭",
    "PTE": "臺灣屏東地方法院屏東簡易庭", "CPE": "臺灣屏東地方法院潮州簡易庭",
    "ILE": "臺灣宜蘭地方法院宜蘭簡易庭", "LTE": "臺灣宜蘭地方法院羅東簡易庭",
    "HLE": "臺灣花蓮地方法院花蓮簡易庭", 
    "TTE": "臺灣臺東地方法院臺東簡易庭",
    "MKE": "臺灣澎湖地方法院馬公簡易庭", 
    "KME": "福建金門地方法院金城簡易庭", 
    "LCE": "福建連江地方法院連江簡易庭",
    "KSY": "臺灣高雄少年及家事法院", "IPC": "智慧財產及商業法院"
}

@router.post("/get_history")
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
    options.add_argument('--single-process')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"

    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    elif os.path.exists("/usr/lib/chromium-browser/chromedriver"):
        service = Service("/usr/lib/chromium-browser/chromedriver")
    else:
        service = Service(ChromeDriverManager().install())
        
    driver = None
    history_results = []
    
    try:
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 12)
        
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
        print(f"❌ 爬蟲發生錯誤: {e}")
    finally:
        if driver:
            driver.quit()
        
    return {"history": history_results}