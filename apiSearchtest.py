import os
import sys
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain

# 1. 讀取 .env 檔案
load_dotenv() 

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("🚨 錯誤：找不到 GOOGLE_API_KEY！")
    sys.exit()

os.environ["GOOGLE_API_KEY"] = api_key

# 準備內部資料
docs = [
    Document(page_content="在 Unity 遊戲引擎中，NavMesh (導航網格) 是用來實現角色自動尋路的核心元件。若要讓車輛在沒有固定目的地的網格上隨機移動，並在遇見轉彎時自動轉向，可以透過 Raycast 偵測前方障礙物或路徑邊緣，結合 NavMeshAgent 的 velocity 屬性來動態計算轉向角度。")
]

# 切塊
text_splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=20)
splits = text_splitter.split_documents(docs)

# 3. 向量化 (使用最新官方推薦的 gemini-embedding-2-preview)
vectorstore = Chroma.from_documents(
    documents=splits, 
    embedding=GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-2-preview",
        google_api_key=api_key
    ) 
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 2})

# 4. 初始化 Gemini 對話模型
llm = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash", 
    temperature=0,
    google_api_key=api_key
)

# 設計提示詞
system_prompt = (
    "你是一位專業的技術助理。請使用以下提供的 [參考內容] 來回答問題。"
    "如果你不知道答案，請直接說不知道，不要編造資訊。"
    "\n\n"
    "[參考內容]："
    "{context}"
)

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{input}"),
])

# 串接工作流
question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, question_answer_chain)

# 提問與執行
question = "在 Unity 中要怎麼讓車輛遇到轉彎才自動轉向？"
print(f"使用者提問：{question}")

response = rag_chain.invoke({"input": question})
print("\nAI 回覆：")
print(response["answer"])