# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered customer service agent for order management, built with FastAPI + LangChain + Groq (Llama 3.3). The system uses a ReAct agent to guide customers through a strict 3-step ordering workflow via chat. All UI and prompts are in Traditional Chinese (繁體中文).

## Commands

```bash
# Start dev server (auto-reloads on file changes)
uvicorn main:app --reload --port 8000

# Reset database and restart server
./reset.sh

# Run integration test (requires server running on port 8000)
python test_chat.py
# Results logged to test_chat.log

# Install dependencies
pip install -r requirements.txt
```

## Environment

- Python 3.11 (conda env: `poc`)
- Requires `GROQ_API_KEY` in `.env` file
- SQLite database `product.db` is auto-created and seeded on first startup
- Chat UI: `http://localhost:8000` | Admin panel: `http://localhost:8000/admin`

## Architecture

**Request flow:** Browser → FastAPI (`main.py`) → LangChain ReAct Agent (`agent.py`) → Tools (`tools.py`) → SQLite (`database.py`)

### Key files

- **main.py** — FastAPI app with `/api/chat` endpoint. Manages in-memory session histories (dict of session_id → message list, truncated to 20 messages).
- **agent.py** — Builds the LangChain ReAct agent via `langgraph.prebuilt.create_react_agent`. Contains the system prompt that enforces the 3-step ordering workflow. Uses `ChatGroq` with `llama-3.3-70b-versatile`.
- **tools.py** — 8 `@tool`-decorated functions that are the agent's capabilities. All tools interact with SQLite directly (no ORM). Tools return formatted strings that the LLM interprets and relays to the user.
- **database.py** — SQLite setup with `get_connection()`, `init_db()` (creates 5 tables), and `seed_sample_data()` (3 customers, 5 products).
- **models.py** — Pydantic models for `ChatRequest` and `ChatResponse`.
- **static/** — Vanilla HTML/JS/CSS frontend (chat UI + admin dashboard).

### 3-Step Ordering Workflow (enforced by system prompt)

1. **Step 1 — Customer registration:** Collect name/address/phone → user confirms → `register_customer`
2. **Step 2 — Order draft:** Show products via `query_products` → user selects items → `create_order_draft` → user confirms. No delivery/payment questions allowed in this step.
3. **Step 3 — Delivery & payment:** Ask delivery (專車/郵寄) and payment (現金/匯款/貨到付款) → `preview_final_order` → user confirms → `confirm_order` writes to DB and deducts stock.

### Database Tables

5 tables: `customer`, `product`, `orders`, `customer_order_detail`, `wastage`. Foreign keys are enforced via `PRAGMA foreign_keys = ON`. The `confirm_order` tool is the only one that writes orders — it inserts into `orders` + `customer_order_detail` and updates `product.stock` in a single transaction.

### Tool Design Pattern

Tools that modify orders follow a draft→preview→confirm pattern. `create_order_draft` and `preview_final_order` are read-only validation/calculation tools. Only `confirm_order` and `record_wastage` perform writes. Tool return strings include instructions to the LLM (e.g., "you must display all items to the customer") to control agent behavior.
