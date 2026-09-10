import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# 1. 司法院法院代碼對照表
# ==========================================
COURT_MAPPING = {
    "TPS": "最高法院", "TPA": "最高行政法院", 
    "TPH": "臺灣高等法院", "TCH": "臺灣高等法院臺中分院", 
    "TNH": "臺灣高等法院臺南分院", "KSH": "臺灣高等法院高雄分院", 
    "HLH": "臺灣高等法院花蓮分院", "KMD": "福建高等法院金門分院",
    "TPB": "臺北高等行政法院", "TCB": "臺中高等行政法院", "KSB": "高雄高等行政法院",
    "TPD": "臺灣臺北地方法院", "SLD": "臺灣士林地方法院", "PCD": "臺灣新北地方法院", 
    "TYD": "臺灣桃園地方法院", "SCD": "臺灣新竹地方法院", "MLD": "臺灣苗栗地方法院", 
    "TCD": "臺灣臺中地方法院", "NTD": "臺灣南投地方法院", "CHD": "臺灣彰化地方法院", 
    "ULD": "臺灣雲林地方法院", "CYD": "臺灣嘉義地方法院", "TND": "臺灣臺南地方法院", 
    "KSD": "臺灣高雄地方法院", "CTD": "臺灣橋頭地方法院", "PTD": "臺灣屏東地方法院", 
    "TTD": "臺灣臺東地方法院", "HLD": "臺灣花蓮地方法院", "ILD": "臺灣宜蘭地方法院", 
    "KLD": "臺灣基隆地方法院", "PHD": "臺灣澎湖地方法院", "KMD": "福建金門地方法院", 
    "LCD": "福建連江地方法院"
}

# ==========================================
# 2. 處理你的 JSON 資料
# ==========================================
json_data = '''
{
    "id": "ILDM,114,簡,820,20260825,2",
    "year": "114",
    "case_type": "簡",
    "case_no": "820",
    "date": "20260825",
    "title": "毒品危害防制條例",
    "content": "臺灣宜蘭地方法院刑事裁定...",
    "pdf_url": "https://data.judicial.gov.tw/jdg/api/JDocFile/ILDM/114%2c%e7%b0%a1%2c820%2c20260825%2c2/pdf"
}
'''

data = json.loads(json_data)
raw_id = data["id"].split(",")[0]  
court_code = raw_id[:3]  
search_court = COURT_MAPPING.get(court_code, "未知法院")
search_year = data["year"]
search_word = data["case_type"]
search_num = data["case_no"]
json_date = data["date"]

print(f"[*] 解析完成！準備查詢: {search_court} {search_year}年度 {search_word}字 第{search_num}號")

# ==========================================
# 3. Selenium 爬蟲主程式
# ==========================================
def scrape_judgment_history():
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') # 測試成功後可以解開註解，讓瀏覽器在背景執行
    options.add_argument('--disable-notifications')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 10)
    
    try:
        print("[*] 正在進入司法院裁判書查詢系統...")
        driver.get("https://judgment.judicial.gov.tw/FJUD/default.aspx")
        
        # 步驟 A: 填寫單一搜尋表單
        search_query = f"{search_court}{search_year}{search_word}{search_num}"
        print(f"[*] 正在輸入檢索字詞: {search_query}")
        
        search_input = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[placeholder*='可輸入法院名稱']")
        ))
        search_input.clear()
        search_input.send_keys(search_query)
        
        try:
            submit_btn = driver.find_element(
                By.XPATH, 
                "//button[contains(text(), '送出查詢')] | //input[@value='送出查詢']"
            )
            submit_btn.click()
        except:
            print("[*] 找不到送出按鈕，改用 Enter 鍵送出")
            search_input.send_keys(Keys.RETURN)

        # ==========================================
        # 🌟 步驟 B: 切換 iframe 並精準比對日期
        # ==========================================
        print("[*] 正在等待搜尋結果框架載入...")
        try:
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "iframe-data")))
        except Exception as e:
            print("[!] 無法切換至 iframe-data，繼續在當前頁面嘗試。")
            time.sleep(2)
        
        # 日期轉換 (西元轉民國)
        tw_year = str(int(json_date[:4]) - 1911)
        tw_month = json_date[4:6]
        tw_day = json_date[6:8]
        target_date_str = f"{tw_year}.{tw_month}.{tw_day}"
        print(f"[*] 目標比對日期為: {target_date_str}")
        
        try:
            # 等待表格載入
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
            
            # 精準尋找擁有「目標日期」的那一列，並點擊裡面的超連結
            xpath_query = f"//tr[td[contains(text(), '{target_date_str}')]]//a"
            exact_match_link = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_query)))
            
            print(f"[*] 成功找到日期為 {target_date_str} 的案件，點擊進入內文...")
            exact_match_link.click()
            
        except Exception as e:
            print(f"[!] 找不到完全符合日期的案件，將退回預設點擊第一筆結果。")
            first_result = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.hlTitle_scroll, #hlTitle")))
            first_result.click()

        # ==========================================
        # 🌟 步驟 C: 抓取歷審裁判清單
        # ==========================================
        print("[*] 正在尋找歷審裁判資料...")
        
        # 因為點擊連結後網頁會跳轉，需要等待新頁面的歷審區塊載入
        history_links = wait.until(EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "div.panel-body ul li a[href*='data.aspx']")
        ))
        
        print("\n" + "="*50)
        print("🎯 成功獲取歷審裁判紀錄：")
        for idx, link in enumerate(history_links, 1):
            title = link.text.strip()
            # 將相對路徑補齊成絕對路徑，方便點擊
            url = link.get_attribute("href") 
            if not url.startswith("http"):
                url = "https://judgment.judicial.gov.tw/FJUD/" + url
                
            print(f"[{idx}] {title}")
            print(f"    連結: {url}")
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"[!] 爬蟲執行過程中發生錯誤: {e}")
        
    finally:
        print("[*] 爬蟲結束，關閉瀏覽器。")
        time.sleep(2)
        driver.quit()

# ==========================================
# 4. 執行程式
# ==========================================
if __name__ == "__main__":
    scrape_judgment_history()