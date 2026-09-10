from fastapi import FastAPI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
os.environ["GOOGLE_API_KEY"] = api_key

app = FastAPI()

# 設定 CORS，讓網頁前端可以順利呼叫 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class MultiQAQuery(BaseModel):
    judgments_content: list[str]
    question: str

@app.post("/api/ask_multiple")
def ask_ai_multiple(query: MultiQAQuery):
    if not query.judgments_content:
        return {"answer": "目前沒有任何案件資料可供閱讀。"}

    # 💡 為了確保伺服器回應速度，我們設定最多一次讓 AI 閱讀前 30 筆篩選結果
    # (30 筆判決書大約只有幾萬 Token，Gemini 1.5 Flash 處理起來輕而易舉)
    texts_to_read = query.judgments_content[:30]
    
    # 將所有判決書內容合併成一個巨大的字串，中間用分隔線隔開
    context = "\n\n---\n\n".join(texts_to_read)
    
    # 💡 直接呼叫 Gemini 模型，不再使用 Chroma
    llm = ChatGoogleGenerativeAI(model="gemini-3.6-flash", temperature=0)
    
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "你是一位專業的法律助理。請綜合以下提供的 [篩選後裁判書內容] 來回答問題。\n"
                   "回答時，請務必明確指出是依據哪一個案號的判決。\n"
                   "如果你不知道答案，請直接說不知道，不要編造資訊。\n\n"
                   "[篩選後裁判書內容]：\n{context}"),
        ("human", "{input}")
    ])
    
    # 串接 Prompt 與模型並執行
    chain = prompt_template | llm
    
    response = chain.invoke({
        "context": context,
        "input": query.question
    })
    
    return {"answer": response.content}