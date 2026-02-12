import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "product.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer (
            customer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_address TEXT NOT NULL,
            customer_phone TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS product (
            product_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name  TEXT NOT NULL,
            unit          TEXT NOT NULL,
            price         REAL NOT NULL,
            stock         INTEGER NOT NULL DEFAULT 0,
            safety_stock  INTEGER NOT NULL DEFAULT 0,
            supplier      TEXT,
            specification TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wastage (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name  TEXT NOT NULL,
            product_id    INTEGER NOT NULL,
            loss_quantity INTEGER NOT NULL,
            FOREIGN KEY (product_id) REFERENCES product(product_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name   TEXT NOT NULL,
            delivery_method TEXT NOT NULL,
            payment_method  TEXT NOT NULL,
            total_price     REAL NOT NULL DEFAULT 0,
            is_delivered    INTEGER NOT NULL DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_order_detail (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id  INTEGER NOT NULL,
            product_id   INTEGER NOT NULL,
            order_id     INTEGER NOT NULL,
            quantity     INTEGER NOT NULL,
            unit_price   REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (customer_id) REFERENCES customer(customer_id),
            FOREIGN KEY (product_id)  REFERENCES product(product_id),
            FOREIGN KEY (order_id)    REFERENCES orders(order_id)
        )
    """)

    conn.commit()
    conn.close()


def seed_sample_data():
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM customer").fetchone()[0]
    if count > 0:
        conn.close()
        return

    conn.executemany(
        "INSERT INTO customer (customer_name, customer_address, customer_phone) VALUES (?, ?, ?)",
        [
            ("王大明", "台北市信義區信義路五段7號", "0912345678"),
            ("李小華", "台中市西屯區台灣大道四段1號", "0923456789"),
            ("張美玲", "高雄市前鎮區中山二路2號", "0934567890"),
        ],
    )

    conn.executemany(
        "INSERT INTO product (product_name, unit, price, stock, safety_stock, supplier, specification) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("蘋果", "箱", 500, 100, 20, "台灣水果商", "每箱20斤"),
            ("香蕉", "箱", 300, 80, 15, "台灣水果商", "每箱15斤"),
            ("牛奶", "瓶", 45, 200, 50, "鮮奶供應商", "1000ml"),
            ("雞蛋", "盒", 60, 150, 30, "養雞場", "每盒30顆"),
            ("白米", "包", 250, 60, 10, "米商", "每包5公斤"),
        ],
    )

    conn.commit()
    conn.close()
