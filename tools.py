from langchain_core.tools import tool
from database import get_connection


# ============ Function Call 1: 建立客戶資料 ============

@tool
def register_customer(customer_name: str, customer_address: str, customer_phone: str) -> str:
    """【下單步驟一】建立或更新客戶基本資料，存入資料庫。
    需要提供：客戶名稱、地址、電話。
    Register or update customer info and save to database."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM customer WHERE customer_name = ?",
            (customer_name,),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE customer SET customer_address = ?, customer_phone = ? WHERE customer_id = ?",
                (customer_address, customer_phone, existing["customer_id"]),
            )
            conn.commit()
            return (
                f"客戶資料已更新！\n"
                f"客戶ID: {existing['customer_id']}\n"
                f"名稱: {customer_name}\n"
                f"地址: {customer_address}\n"
                f"電話: {customer_phone}"
            )

        cursor = conn.execute(
            "INSERT INTO customer (customer_name, customer_address, customer_phone) VALUES (?, ?, ?)",
            (customer_name, customer_address, customer_phone),
        )
        conn.commit()
        return (
            f"客戶資料建立成功！\n"
            f"客戶ID: {cursor.lastrowid}\n"
            f"名稱: {customer_name}\n"
            f"地址: {customer_address}\n"
            f"電話: {customer_phone}"
        )
    except Exception as e:
        conn.rollback()
        return f"建立客戶資料時發生錯誤: {str(e)}"
    finally:
        conn.close()


# ============ Function Call 2: 建立訂單草稿 ============

@tool
def create_order_draft(customer_name: str, items: list[dict]) -> str:
    """【下單步驟二】建立訂單草稿，驗證產品和庫存，計算金額，回傳明細讓客戶確認或修改。
    items 是列表，每個元素包含 product_name(str) 和 quantity(int)。
    此工具只做驗證和計算，不會寫入資料庫。客戶可以要求修改後再次呼叫此工具。
    Create order draft. items: list of {product_name, quantity}. Only validates, does NOT save to DB."""
    conn = get_connection()
    try:
        customer = conn.execute(
            "SELECT customer_id FROM customer WHERE customer_name = ?",
            (customer_name,),
        ).fetchone()
        if not customer:
            return f"找不到客戶「{customer_name}」，請先使用 register_customer 建立客戶資料。"

        total = 0
        draft_lines = []
        for item in items:
            product = conn.execute(
                "SELECT product_id, product_name, price, stock, unit FROM product WHERE product_name LIKE ?",
                (f"%{item['product_name']}%",),
            ).fetchone()
            if not product:
                return f"找不到產品「{item['product_name']}」。請使用 query_products 查看可訂購的產品。"
            if product["stock"] < item["quantity"]:
                return (
                    f"產品「{product['product_name']}」庫存不足"
                    f"（庫存: {product['stock']}，需要: {item['quantity']}）。"
                )
            subtotal = product["price"] * item["quantity"]
            total += subtotal
            draft_lines.append(
                f"- {product['product_name']} x {item['quantity']}{product['unit']}"
                f"（單價: {product['price']}元，小計: {int(subtotal)}元）"
            )

        result = "📋 訂單草稿：\n"
        result += f"客戶: {customer_name}\n"
        result += "\n".join(draft_lines) + "\n"
        result += f"總價格: {int(total)} 元\n"
        result += "\n請將以上完整內容顯示給客戶，並問「訂單內容是否正確？需要修改請告訴我」"
        return result
    except Exception as e:
        return f"建立訂單草稿時發生錯誤: {str(e)}"
    finally:
        conn.close()


# ============ Function Call 3: 確認訂單並選擇配送 ============

@tool
def confirm_order(
    customer_name: str,
    items: list[dict],
    delivery_method: str,
    payment_method: str,
) -> str:
    """【下單步驟三】客戶確認訂單內容和配送方式後，正式建立訂單寫入資料庫。
    items 是列表，每個元素包含 product_name(str) 和 quantity(int)。
    delivery_method: 專車 或 郵寄。
    Finalize and save order to DB after customer confirmation."""
    conn = get_connection()
    try:
        customer = conn.execute(
            "SELECT customer_id FROM customer WHERE customer_name = ?",
            (customer_name,),
        ).fetchone()
        if not customer:
            return f"找不到客戶「{customer_name}」。"

        total = 0
        validated_items = []
        for item in items:
            product = conn.execute(
                "SELECT product_id, product_name, price, stock FROM product WHERE product_name LIKE ?",
                (f"%{item['product_name']}%",),
            ).fetchone()
            if not product:
                return f"找不到產品「{item['product_name']}」。"
            if product["stock"] < item["quantity"]:
                return (
                    f"產品「{product['product_name']}」庫存不足"
                    f"（庫存: {product['stock']}，需要: {item['quantity']}）。"
                )
            total += product["price"] * item["quantity"]
            validated_items.append((product, item["quantity"]))

        cursor = conn.execute(
            "INSERT INTO orders (customer_name, delivery_method, payment_method, total_price) VALUES (?, ?, ?, ?)",
            (customer_name, delivery_method, payment_method, total),
        )
        order_id = cursor.lastrowid

        for product, qty in validated_items:
            conn.execute(
                "INSERT INTO customer_order_detail (customer_id, product_id, order_id, quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
                (customer["customer_id"], product["product_id"], order_id, qty, product["price"]),
            )
            conn.execute(
                "UPDATE product SET stock = stock - ? WHERE product_id = ?",
                (qty, product["product_id"]),
            )

        conn.commit()
        return (
            f"✅ 訂單建立成功！\n"
            f"訂單編號: {order_id}\n"
            f"客戶: {customer_name}\n"
            f"總價格: {int(total)} 元\n"
            f"配送方式: {delivery_method}\n"
            f"收款方式: {payment_method}"
        )
    except Exception as e:
        conn.rollback()
        return f"建立訂單時發生錯誤: {str(e)}"
    finally:
        conn.close()


# ============ 其他功能 ============

@tool
def query_products(product_name: str = "") -> str:
    """查詢產品資訊。可以用產品名稱搜尋，或不輸入名稱列出所有產品。
    Query product information by name, or list all products if no name given."""
    conn = get_connection()
    if product_name:
        rows = conn.execute(
            "SELECT * FROM product WHERE product_name LIKE ?",
            (f"%{product_name}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM product").fetchall()
    conn.close()

    if not rows:
        return "找不到符合的產品。"

    result = []
    for r in rows:
        result.append(
            f"產品ID: {r['product_id']}, 名稱: {r['product_name']}, "
            f"價格: {r['price']}元/{r['unit']}, 庫存: {r['stock']}{r['unit']}, "
            f"供應商: {r['supplier']}, 規格: {r['specification']}"
        )
    return "\n".join(result)


@tool
def check_stock(product_name: str) -> str:
    """檢查特定產品的庫存狀況，如果低於安全庫存會發出警告。
    Check stock level for a product and warn if below safety stock."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM product WHERE product_name LIKE ?",
        (f"%{product_name}%",),
    ).fetchone()
    conn.close()

    if not row:
        return f"找不到產品「{product_name}」。"

    status = "正常"
    if row["stock"] <= row["safety_stock"]:
        status = "⚠️ 低於安全庫存，需要補貨！"

    return (
        f"產品: {row['product_name']}\n"
        f"目前庫存: {row['stock']}{row['unit']}\n"
        f"安全庫存: {row['safety_stock']}{row['unit']}\n"
        f"庫存狀態: {status}"
    )


@tool
def query_orders(customer_name: str = "", order_id: int = 0) -> str:
    """查詢訂單。可以用客戶名稱或訂單編號查詢。
    Query orders by customer name or order ID."""
    conn = get_connection()

    if order_id:
        order = conn.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        if not order:
            conn.close()
            return f"找不到訂單編號 {order_id}。"

        details = conn.execute(
            """SELECT d.quantity, d.unit_price, p.product_name, p.unit
               FROM customer_order_detail d
               JOIN product p ON d.product_id = p.product_id
               WHERE d.order_id = ?""",
            (order_id,),
        ).fetchall()
        conn.close()

        items_str = "\n".join(
            f"  - {d['product_name']} x {d['quantity']}{d['unit']} (單價: {d['unit_price']}元)"
            for d in details
        )
        return (
            f"訂單編號: {order['order_id']}\n"
            f"客戶: {order['customer_name']}\n"
            f"配送方式: {order['delivery_method']}\n"
            f"收款方式: {order['payment_method']}\n"
            f"總價格: {order['total_price']} 元\n"
            f"訂單明細:\n{items_str}"
        )

    if customer_name:
        orders = conn.execute(
            "SELECT * FROM orders WHERE customer_name LIKE ?",
            (f"%{customer_name}%",),
        ).fetchall()
        conn.close()

        if not orders:
            return f"找不到客戶「{customer_name}」的訂單。"

        result = []
        for o in orders:
            result.append(
                f"訂單編號: {o['order_id']}, 總價格: {o['total_price']}元, "
                f"配送: {o['delivery_method']}, 收款: {o['payment_method']}"
            )
        return "\n".join(result)

    conn.close()
    return "請提供客戶名稱或訂單編號來查詢。"


@tool
def record_wastage(product_name: str, loss_quantity: int) -> str:
    """記錄產品損耗。會自動扣除庫存。
    Record product wastage/loss. Stock will be automatically deducted."""
    conn = get_connection()
    try:
        product = conn.execute(
            "SELECT product_id, product_name, stock FROM product WHERE product_name LIKE ?",
            (f"%{product_name}%",),
        ).fetchone()
        if not product:
            conn.close()
            return f"找不到產品「{product_name}」。"

        if product["stock"] < loss_quantity:
            conn.close()
            return (
                f"損耗數量 ({loss_quantity}) 超過目前庫存 ({product['stock']})，請確認數量。"
            )

        conn.execute(
            "INSERT INTO wastage (product_name, product_id, loss_quantity) VALUES (?, ?, ?)",
            (product["product_name"], product["product_id"], loss_quantity),
        )
        conn.execute(
            "UPDATE product SET stock = stock - ? WHERE product_id = ?",
            (loss_quantity, product["product_id"]),
        )
        conn.commit()
        new_stock = product["stock"] - loss_quantity
        return (
            f"損耗記錄成功！\n"
            f"產品: {product['product_name']}\n"
            f"損耗數量: {loss_quantity}\n"
            f"剩餘庫存: {new_stock}"
        )
    except Exception as e:
        conn.rollback()
        return f"記錄損耗時發生錯誤: {str(e)}"
    finally:
        conn.close()
