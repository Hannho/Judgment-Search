import requests

def get_api_token(username, password):
    # 1. 設定驗證權限的服務路徑
    url = "https://data.judicial.gov.tw/jdg/api/Auth"
    
    # 2. 準備 JSON 格式的 Request Body[cite: 1]
    payload = {
        "user": username,
        "password": password
    }
    
    # 3. 確保 Request Header 的 Content-Type 為 application/json[cite: 1]
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        # 使用 POST 方法發送請求[cite: 1]
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        
        # 判斷是否成功取得 Token
        if "Token" in data:
            print("✅ 成功取得 Token:", data["Token"])
            # 這組 Token 在驗證通過後有 6 小時的時效[cite: 1]
            return data["Token"]
        elif "error" in data:
            print("❌", data["error"]) # 如果未通過，會回傳驗證失敗[cite: 1]
            return None
        else:
            print("未知的回應格式:", data)
            return None
            
    except Exception as e:
       print("連線發生錯誤 (請確認是否在凌晨 0 點至 6 點間執行):", e)

# 請將這裡替換成你剛剛拿到的帳號與密碼
my_user = 'hannidozone'
my_pwd = "Hann0829"

# 執行驗證
if __name__ == "__main__":
    token = get_api_token(my_user, my_pwd)