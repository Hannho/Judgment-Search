import os
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain

# 1. 填入你剛剛取得的 OpenAI API Key (保留雙引號)

from dotenv import load_dotenv

# 讀取 .env 檔案中的變數
load_dotenv() 

# 從環境變數中取得金鑰，不要寫死在程式碼裡
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
# 2. 準備內部資料 (這裡模擬一份關於車輛尋路的說明)
docs = [
    Document(page_content="在 Unity 遊戲引擎中，NavMesh (導航網格) 是用來實現角色自動尋路的核心元件。若要讓車輛在沒有固定目的地的網格上隨機移動，並在遇見轉彎時自動轉向，可以透過 Raycast 偵測前方障礙物或路徑邊緣，結合 NavMeshAgent 的 velocity 屬性來動態計算轉向角度。")
]

# 切塊
text_splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=20)
splits = text_splitter.split_documents(docs)

# 3. 向量化與儲存 (這裡會消耗微量的 OpenAI API 費用，將文字轉為向量)
vectorstore = Chroma.from_documents(
    documents=splits, 
    embedding=OpenAIEmbeddings(model="text-embedding-3-small") # 指定最新的向量模型，便宜且精準
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 2})

# 4. 初始化 OpenAI 對話模型
llm = ChatOpenAI(
    model="gpt-3.5-turbo", # 也可以換成 gpt-4o 或 gpt-4o-mini
    temperature=0          # 設為 0 代表回答越精確、不隨便發散
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

# 5. 串接工作流
question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, question_answer_chain)

# 6. 提問與執行
question = "在 Unity 中要怎麼讓車輛遇到轉彎才自動轉向？"
print(f"使用者提問：{question}")

response = rag_chain.invoke({"input": question})
print("\nAI 回覆：")
print(response["answer"])
