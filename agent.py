import os
import re
import json
import logging
from typing import Annotated, Literal
from typing_extensions import TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from tools import (
    register_customer,
    create_order_draft,
    preview_final_order,
    confirm_order,
    query_products,
    check_stock,
    query_orders,
    record_wastage,
)

load_dotenv()

logger = logging.getLogger(__name__)

# ============ State Schema ============

class OrderState(TypedDict):
    messages: Annotated[list, add_messages]
    workflow_phase: str  # idle / collect_info / confirm_info / collect_items / confirm_items / collect_delivery / preview_order
    customer_name: str | None
    customer_address: str | None
    customer_phone: str | None
    customer_id: int | None
    items: list[dict] | None  # [{product_name, quantity}]
    delivery_method: str | None
    payment_method: str | None


# ============ LLM ============

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
)

# ============ Pydantic models for structured extraction ============

class CustomerInfo(BaseModel):
    customer_name: str = Field(description="客戶名稱")
    customer_address: str = Field(description="客戶地址")
    customer_phone: str = Field(description="客戶電話")


class OrderItem(BaseModel):
    product_name: str = Field(description="產品名稱")
    quantity: int = Field(description="數量")


class OrderItems(BaseModel):
    items: list[OrderItem] = Field(description="品項列表")


class DeliveryInfo(BaseModel):
    delivery_method: str = Field(description="配送方式：專車 或 郵寄")
    payment_method: str = Field(description="收款方式：現金、匯款 或 貨到付款")


# ============ General agent (for non-ordering queries) ============

GENERAL_PROMPT = "你是客戶服務助手，用繁體中文回覆。可以查產品、查庫存、查訂單、記損耗。"

general_agent = create_react_agent(
    llm,
    [query_products, check_stock, query_orders, record_wastage],
    prompt=GENERAL_PROMPT,
)

# ============ Helpers ============

def _is_confirm(msg: str) -> bool:
    """Check if the user message is a confirmation."""
    keywords = ["確認", "確定", "沒問題", "ok", "OK", "Ok", "對", "是的", "好的", "好"]
    msg = msg.strip()
    return any(kw == msg or msg.startswith(kw) for kw in keywords) and len(msg) < 20


def _is_order_intent(msg: str) -> bool:
    """Check if the user wants to place an order."""
    return any(kw in msg for kw in ["下單", "訂購", "我要訂", "下訂", "我要買"])



def _clean_tool_result(result: str) -> str:
    """Remove embedded LLM instructions (after ---) from tool results."""
    if "---" in result:
        return result.split("---")[0].strip()
    return result


def _extract_int_field(text: str, keyword: str) -> int | None:
    """Extract an integer value after a keyword like '客戶ID: 3'."""
    for line in text.split("\n"):
        if keyword in line:
            match = re.search(r'(\d+)', line.split(keyword)[-1])
            if match:
                return int(match.group(1))
    return None


# ============ Phase handlers ============

def handle_idle(state: OrderState, user_msg: str) -> dict:
    if _is_order_intent(user_msg):
        return {
            "messages": [AIMessage(content="您好，我們先建立您的基本資料。請提供您的 名稱、地址、電話。")],
            "workflow_phase": "collect_info",
        }
    # General query - delegate to ReAct agent
    result = general_agent.invoke({"messages": state["messages"]})
    ai_msg = result["messages"][-1]
    return {"messages": [ai_msg]}


def handle_collect_info(state: OrderState, user_msg: str) -> dict:
    try:
        structured_llm = llm.with_structured_output(CustomerInfo)
        info = structured_llm.invoke(
            f"從以下訊息中提取客戶的名稱、地址、電話。訊息：{user_msg}"
        )
        reply = (
            f"請確認您的資料：\n"
            f"- 名稱：{info.customer_name}\n"
            f"- 地址：{info.customer_address}\n"
            f"- 電話：{info.customer_phone}\n"
            f"正確請回覆「確認」"
        )
        return {
            "messages": [AIMessage(content=reply)],
            "workflow_phase": "confirm_info",
            "customer_name": info.customer_name,
            "customer_address": info.customer_address,
            "customer_phone": info.customer_phone,
        }
    except Exception as e:
        logger.error(f"Failed to parse customer info via LLM: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content="抱歉，我無法識別您的資料。請提供您的 名稱、地址、電話。")],
        }


def handle_confirm_info(state: OrderState, user_msg: str) -> dict:
    if _is_confirm(user_msg):
        # Register customer
        reg_result = register_customer.invoke({
            "customer_name": state["customer_name"],
            "customer_address": state["customer_address"],
            "customer_phone": state["customer_phone"],
        })
        customer_id = _extract_int_field(reg_result, "客戶ID")

        # Get product list
        products = query_products.invoke({"product_name": ""})

        reply = (
            f"客戶資料已建立！\n\n"
            f"以下是我們的產品列表（也可到 http://localhost:8000/products 查看）：\n\n"
            f"{products}\n\n"
            f"請用產品名稱和數量來選購，例如「蘋果*2 牛奶*3」。"
        )
        return {
            "messages": [AIMessage(content=reply)],
            "workflow_phase": "collect_items",
            "customer_id": customer_id,
        }
    else:
        return {
            "messages": [AIMessage(content="好的，請重新提供您的 名稱、地址、電話。")],
            "workflow_phase": "collect_info",
        }


def handle_collect_items(state: OrderState, user_msg: str) -> dict:
    try:
        structured_llm = llm.with_structured_output(OrderItems)
        parsed = structured_llm.invoke(
            f"從以下訊息中提取訂單品項（產品名稱和數量）。訊息：{user_msg}"
        )
        items = [{"product_name": i.product_name, "quantity": i.quantity} for i in parsed.items]
    except Exception as e:
        logger.error(f"Failed to parse order items via LLM: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content="抱歉，我無法解析您的品項。請告訴我產品名稱和數量，例如「蘋果 2箱、牛奶 3箱」。")],
        }

    # Validate via create_order_draft
    draft_result = create_order_draft.invoke({
        "customer_name": state["customer_name"],
        "items": items,
    })

    if "找不到" in draft_result or "庫存不足" in draft_result:
        return {
            "messages": [AIMessage(content=f"{draft_result}\n\n請重新選擇品項。")],
        }

    clean_draft = _clean_tool_result(draft_result)
    reply = f"{clean_draft}\n\n訂單內容是否正確？需要修改請告訴我，確認請回覆「確認」。"
    return {
        "messages": [AIMessage(content=reply)],
        "workflow_phase": "confirm_items",
        "items": items,
    }


def handle_confirm_items(state: OrderState, user_msg: str) -> dict:
    if _is_confirm(user_msg):
        return {
            "messages": [AIMessage(content="請問配送方式要選擇 專車 還是 郵寄？收款方式是 現金、匯款 還是 貨到付款？")],
            "workflow_phase": "collect_delivery",
        }

    # User wants to modify - use LLM to understand modification
    try:
        structured_llm = llm.with_structured_output(OrderItems)
        parsed = structured_llm.invoke(
            f"用戶目前的訂單品項為：{json.dumps(state.get('items', []), ensure_ascii=False)}\n"
            f"用戶說：{user_msg}\n"
            f"請根據用戶的修改意圖，產生完整的更新後品項列表。"
        )
        merged = [{"product_name": i.product_name, "quantity": i.quantity} for i in parsed.items]
    except Exception as e:
        logger.error(f"Failed to parse item modification via LLM: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content="抱歉，我無法理解您的修改。請告訴我要修改的品項和數量。")],
        }

    # Validate merged items
    draft_result = create_order_draft.invoke({
        "customer_name": state["customer_name"],
        "items": merged,
    })

    if "找不到" in draft_result or "庫存不足" in draft_result:
        return {
            "messages": [AIMessage(content=f"{draft_result}\n\n請重新告訴我要修改的內容。")],
        }

    clean_draft = _clean_tool_result(draft_result)
    reply = f"{clean_draft}\n\n訂單內容是否正確？需要修改請告訴我，確認請回覆「確認」。"
    return {
        "messages": [AIMessage(content=reply)],
        "items": merged,
    }


def handle_collect_delivery(state: OrderState, user_msg: str) -> dict:
    try:
        structured_llm = llm.with_structured_output(DeliveryInfo)
        info = structured_llm.invoke(
            f"從以下訊息中提取配送方式（專車/郵寄）和收款方式（現金/匯款/貨到付款）。訊息：{user_msg}"
        )

        preview_result = preview_final_order.invoke({
            "customer_name": state["customer_name"],
            "items": state["items"],
            "delivery_method": info.delivery_method,
            "payment_method": info.payment_method,
        })

        clean_preview = _clean_tool_result(preview_result)
        reply = f"{clean_preview}\n\n以上訂單是否正確？確認請回覆「確認」，需要修改請告訴我。"
        return {
            "messages": [AIMessage(content=reply)],
            "workflow_phase": "preview_order",
            "delivery_method": info.delivery_method,
            "payment_method": info.payment_method,
        }
    except Exception as e:
        logger.error(f"Failed to parse delivery info via LLM: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content="抱歉，我無法識別配送和收款方式。\n請問配送方式要選擇 專車 還是 郵寄？收款方式是 現金、匯款 還是 貨到付款？")],
        }


def handle_preview_order(state: OrderState, user_msg: str) -> dict:
    if _is_confirm(user_msg):
        result = confirm_order.invoke({
            "customer_name": state["customer_name"],
            "items": state["items"],
            "delivery_method": state["delivery_method"],
            "payment_method": state["payment_method"],
        })
        return {
            "messages": [AIMessage(content=result)],
            "workflow_phase": "idle",
            "items": None,
            "delivery_method": None,
            "payment_method": None,
        }
    else:
        return {
            "messages": [AIMessage(content="好的，請問要修改什麼？\n配送方式：專車 或 郵寄\n收款方式：現金、匯款 或 貨到付款")],
            "workflow_phase": "collect_delivery",
        }


# ============ Main dispatch node ============

HANDLERS = {
    "idle": handle_idle,
    "collect_info": handle_collect_info,
    "confirm_info": handle_confirm_info,
    "collect_items": handle_collect_items,
    "confirm_items": handle_confirm_items,
    "collect_delivery": handle_collect_delivery,
    "preview_order": handle_preview_order,
}


def process_message(state: OrderState) -> dict:
    phase = state.get("workflow_phase") or "idle"
    user_msg = state["messages"][-1].content

    # Allow cancellation from any ordering phase
    if phase != "idle" and any(kw in user_msg for kw in ["取消", "取消訂單"]):
        return {
            "messages": [AIMessage(content="訂單已取消。如需重新下單，請告訴我。")],
            "workflow_phase": "idle",
            "items": None,
            "delivery_method": None,
            "payment_method": None,
        }

    handler = HANDLERS.get(phase, handle_idle)
    return handler(state, user_msg)


# ============ Build Graph ============

graph_builder = StateGraph(OrderState)
graph_builder.add_node("process", process_message)
graph_builder.add_edge(START, "process")
graph_builder.add_edge("process", END)

checkpointer = MemorySaver()
agent_executor = graph_builder.compile(checkpointer=checkpointer)
