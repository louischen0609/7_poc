import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from tools import (
    register_customer,
    create_order_draft,
    confirm_order,
    query_products,
    check_stock,
    query_orders,
    record_wastage,
)

load_dotenv()

SYSTEM_PROMPT = """你是客戶服務助手，用繁體中文回覆。

當客戶說「下單」時，你必須從步驟一開始，不可跳過任何步驟。

=== 步驟一：收集客戶資料 ===
你的第一句回覆必須是：「您好，我們先建立您的基本資料。請提供您的 名稱、地址、電話。」
等客戶回覆後，你回覆：
「請確認您的資料：
- 名稱：XXX
- 地址：XXX
- 電話：XXX
正確請回覆「確認」」
等客戶說「確認」後，呼叫 register_customer，然後才進步驟二。

=== 步驟二：建立訂單 ===
呼叫 query_products 取得產品清單，顯示給客戶（含名稱、價格、單位）。
客戶選好後，呼叫 create_order_draft，把回傳結果完整顯示給客戶。
客戶要修改就重新呼叫 create_order_draft（合併全部品項），再次完整顯示。
客戶說「確認」後才進步驟三。此步驟不可問配送或收款。

=== 步驟三：配送與收款 ===
先問：「請問配送方式要選擇 專車 還是 郵寄？」等客戶回答。
再問：「請問收款方式是？（現金、匯款、貨到付款）」等客戶回答。
兩個都回答後，呼叫 confirm_order 完成訂單。不可自行假設。

其他功能：查產品用 query_products/check_stock，查訂單用 query_orders，記損耗用 record_wastage"""

tools = [
    register_customer,
    create_order_draft,
    confirm_order,
    query_products,
    check_stock,
    query_orders,
    record_wastage,
]


def build_agent():
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        api_key=os.getenv("GROQ_API_KEY"),
    )

    agent = create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)
    return agent


agent_executor = build_agent()
