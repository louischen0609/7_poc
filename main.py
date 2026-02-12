from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from langchain_core.messages import HumanMessage

from models import ChatRequest, ChatResponse
from database import init_db, seed_sample_data, get_connection
from agent import agent_executor

ALLOWED_TABLES = {"customer", "product", "orders", "customer_order_detail", "wastage"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_sample_data()
    yield


app = FastAPI(title="AI Customer Service Agent", lifespan=lifespan)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or "default"
    config = {"configurable": {"thread_id": session_id}}

    try:
        result = agent_executor.invoke(
            {"messages": [HumanMessage(content=request.message)]},
            config=config,
        )
        ai_message = result["messages"][-1]
        return ChatResponse(reply=ai_message.content)
    except Exception as e:
        print(f"[Chat Error] session={session_id}, error={type(e).__name__}: {e}")
        return ChatResponse(reply=f"系統處理時發生錯誤，請再試一次。（錯誤：{type(e).__name__}）")


@app.get("/api/admin/table/{table_name}")
async def get_table(table_name: str):
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail="Invalid table name")
    conn = get_connection()
    rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    columns = [desc[0] for desc in conn.execute(f"SELECT * FROM {table_name} LIMIT 0").description] if rows else []
    if not columns:
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    return {
        "columns": columns,
        "rows": [dict(r) for r in rows],
    }


@app.get("/api/admin/order/{order_id}")
async def get_order_detail(order_id: int):
    conn = get_connection()
    order = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        raise HTTPException(status_code=404, detail="Order not found")

    details = conn.execute(
        """SELECT d.quantity, d.unit_price, p.product_name, p.unit,
                  (d.quantity * d.unit_price) as subtotal
           FROM customer_order_detail d
           JOIN product p ON d.product_id = p.product_id
           WHERE d.order_id = ?""",
        (order_id,),
    ).fetchall()
    conn.close()

    return {
        "order": dict(order),
        "items": [dict(d) for d in details],
    }


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/admin")
async def admin():
    return FileResponse("static/admin.html")


@app.get("/products")
async def products():
    return FileResponse("static/products.html")
