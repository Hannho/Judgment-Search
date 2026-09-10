import os
import google.generativeai as genai
from dotenv import load_dotenv

# 讀取 .env 裡面的 GOOGLE_API_KEY
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

print("🔍 正在查詢你的 API Key 支援的模型清單...")
for m in genai.list_models():
    # 只列出支援對話生成的模型
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")