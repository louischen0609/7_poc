# AI Agent 客戶服務系統 - 實作計畫

## Context
建立一個 AI Agent 客戶服務系統。客戶透過 Chat 介面提出需求（下單、配送、查詢等），由 LangChain Agent + Groq API 調用不同 tools 操作 SQLite 資料庫。

## Tech Stack
- **Backend**: Python 3.11 (conda env: poc) + FastAPI
- **Frontend**: 純 HTML + vanilla JS（FastAPI 提供靜態檔案）
- **Database**: SQLite（sqlite3 標準庫，不用 ORM）
- **AI Agent**: LangChain + ChatGroq (llama-3.3-70b-versatile)

## 專案結構
```
0212_product/
├── main.py              # FastAPI 入口
├── database.py          # SQLite 初始化、連線、seed data
├── models.py            # Pydantic models
├── agent.py             # LangChain Agent + Groq 設定
├── tools.py             # 6 個 LangChain tools（核心業務邏輯）
├── requirements.txt     # Python 依賴
├── .env                 # GROQ_API_KEY
├── .gitignore
├── static/
│   ├── index.html       # Chat UI
│   ├── style.css        # 樣式
│   └── app.js           # 前端 JS
└── product.db           # SQLite（啟動時自動建立）
```

## 實作步驟

### Step 1: 環境設定
- 建立 conda env (poc, python=3.11)
- 建立 `requirements.txt`（fastapi, uvicorn, langchain, langchain-groq, python-dotenv）
- 建立 `.env`（GROQ_API_KEY）和 `.gitignore`

### Step 2: 資料庫 (`database.py`)
- 5 個 table：customer, product, wastage(損耗), orders(訂單), customer_order_detail(關聯)
- `init_db()` 建表、`seed_sample_data()` 填入測試資料（3個客戶、5個產品）
- `get_connection()` 回傳帶 row_factory 的連線

### Step 3: Pydantic Models (`models.py`)
- `ChatRequest`（message, session_id）
- `ChatResponse`（reply）

### Step 4: LangChain Tools (`tools.py`) - 6 個工具
1. `query_products` - 查詢產品資訊
2. `check_stock` - 檢查庫存（低於安全庫存時警告）
3. `create_order` - 建立訂單（驗證客戶/產品/庫存 → 寫入 orders + detail + 扣庫存）
4. `query_orders` - 查詢訂單
5. `record_wastage` - 記錄損耗（寫入 wastage + 扣庫存）
6. `manage_customer` - 新增/更新客戶

### Step 5: Agent (`agent.py`)
- ChatGroq (llama-3.3-70b-versatile, temperature=0)
- 繁體中文系統提示詞
- `create_tool_calling_agent` + `AgentExecutor`

### Step 6: FastAPI (`main.py`)
- `POST /api/chat` - 接收訊息、呼叫 agent、回傳回覆
- `GET /` - 提供 index.html
- lifespan hook 初始化 DB + seed data
- 記憶體內對話歷史（dict: session_id → messages）

### Step 7: 前端 (`static/`)
- 簡潔 Chat 介面，送出訊息 → fetch /api/chat → 顯示回覆
- 思考中提示、Enter 送出

## 資料庫 Schema
- **customer**: customer_id(PK), customer_name, customer_address, customer_phone
- **product**: product_id(PK), product_name, unit, price, stock, safety_stock, supplier, specification
- **wastage**: id(PK), product_name, product_id(FK→product), loss_quantity
- **orders**: order_id(PK), customer_name, delivery_method, payment_method, order_amount
- **customer_order_detail**: id(PK), customer_id(FK), product_id(FK), order_id(FK), quantity

## 驗證方式
1. 啟動 server: `uvicorn main:app --reload --port 8000`
2. 開瀏覽器 http://localhost:8000
3. 測試對話：查詢產品 → 下單 → 查訂單 → 記錄損耗
