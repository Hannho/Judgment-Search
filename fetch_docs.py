import requests
import json
import time

# 💡 新增這行：從 clean_data.py 匯入我們寫好的清洗函式
from clean_data import clean_judgments_data

# ⚠️ 請在這裡填入你的帳號與密碼 (這樣每次執行就會自動拿最新 Token)
MY_USER = "hannidozone"
MY_PWD = "Hann0829"

def save_to_file(filename, data):
    """將資料存成 JSON 檔案，方便查看"""
    with open(filename, 'w', encoding='utf-8') as f:
        # ensure_ascii=False 讓中文能正常顯示，indent=4 會自動排版
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"  📁 詳細資料已儲存至目前的資料夾：{filename}")

def get_api_token(username, password):
    url = "https://data.judicial.gov.tw/jdg/api/Auth"
    payload = {"user": username, "password": password}
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        data = response.json()
        
        if "Token" in data:
            print("  ✅ 成功取得最新 Token！")
            return data["Token"]
        else:
            print("  ❌ 取得 Token 失敗！")
            save_to_file("error_auth.json", data)
            return None
    except Exception as e:
        print(f"  ❌ Auth 連線錯誤: {e}")
        return None

def get_jlist(token):
    # 取得7日前裁判書異動清單
    url = "https://data.judicial.gov.tw/jdg/api/JList" 
    payload = {"token": token}
    headers = {"Content-Type": "application/json"}
    
    print("  👉 準備發送請求到 JList...")
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        return response.json()
    except Exception as e:
        print(f"  ❌ JList 連線錯誤: {e}")
        return None

def get_jdoc(token, jid):
    # 依據所輸入的jid，提供該筆裁判書內容
    url = "https://data.judicial.gov.tw/jdg/api/JDoc" 
    payload = {"token": token, "j": jid}
    headers = {"Content-Type": "application/json"}
    
    print(f"  👉 準備發送請求到 JDoc (取得 JID: {jid})...")
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        return response.json()
    except Exception as e:
        print(f"  ❌ JDoc 連線錯誤: {e}")
        return None

if __name__ == "__main__":
    print("🚀 程式開始執行！自動登入中...")
    token = get_api_token(MY_USER, MY_PWD)
    
    if token:
        jlist_data = get_jlist(token)
        save_to_file("debug_jlist.json", jlist_data) 
        
        if isinstance(jlist_data, list) and len(jlist_data) > 0:
            print(f"✅ 成功取得清單！共有 {len(jlist_data)} 天的異動紀錄。")
            
            all_judgments = [] 
            total_fetched = 0
            
            # 💡 外層迴圈：跑遍清單中「每一天」的資料
            for day_data in jlist_data:
                day_date = day_data.get("date", "未知日期")
                day_records = day_data.get("list", [])
                
                if len(day_records) > 0:
                    print(f"\n📌 開始抓取 {day_date} 的異動紀錄，共 {len(day_records)} 筆...")
                    
                    # 💡 內層迴圈：拿掉 [:100] 的限制，抓取當天「所有」裁判書
                    for index, jid in enumerate(day_records):
                        print(f"[{index + 1}/{len(day_records)}] 正在抓取 JID: {jid}")
                        doc_data = get_jdoc(token, jid)
                        
                        if doc_data:
                            if "error" in doc_data:
                                print(f"  ⚠️ 此篇已下架，官方訊息: {doc_data['error']}")
                            all_judgments.append(doc_data)
                            total_fetched += 1
                        
                        # 仍必須維持暫停 1 秒，避免被司法院伺服器封鎖
                        time.sleep(1) 
                else:
                    print(f"⚠️ {day_date} 當天無異動紀錄。")
            
            # 儲存完整的原始資料
            output_raw_file = "all_judgments_raw.json"
            save_to_file(output_raw_file, all_judgments)
            print(f"\n🎉 批次抓取完成！總共抓取了 {total_fetched} 筆資料。")
            
            print("\n⏳ 準備開始清洗資料...")
            clean_judgments_data(output_raw_file, 'cleaned_judgments.json')
            
        else:
            print("❌ 無法解析清單，請查看 debug_jlist.json。")