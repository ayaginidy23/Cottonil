# =============================================================================
# routers/chat.py  -  Chat endpoints
#   GET  /api/chat/demo-users  -> sample accounts for the "Log in as" selector
#   POST /api/chat/shop        -> one turn of the customer & reseller chatbot
#   POST /api/chat/shop/image  -> photo -> similar products
#   POST /api/chat/analyst     -> one question to the management Business Analyst
#   GET  /api/chat/session     -> restore the open chat + the long-term memory
#   POST /api/chat/new         -> "New chat": fold the chat into memory, start fresh
#   DELETE /api/chat/memory    -> "Forget me": delete the long-term memory
# =============================================================================

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..chat import analyst, image_search, memory, shop_assistant
from ..db import fetch_all
from ..llm import LLMError

QUOTA_HELP = ("The free Gemini quota is used up right now. Wait one minute and try again. "
              "If it keeps failing, today's quota is finished: add a second API key in .env "
              "(LLM_API_KEY=key1,key2) or switch LLM_CHAT_MODEL to another model. Details: ")


def _save(assistant, owner, session_id, user_text, reply, payload):
    """Saving the chat must never cost the user their answer."""
    try:
        return memory.save_turn(assistant, owner, session_id, user_text, reply, payload)
    except Exception as e:
        print(f"WARNING: chat not saved: {e}")
        return session_id


def _ai_error(e: Exception) -> HTTPException:
    """Turn AI failures into clear HTTP errors for the UI."""
    if isinstance(e, LLMError):
        if e.rate_limited:
            return HTTPException(429, QUOTA_HELP + str(e))
        return HTTPException(503, str(e))
    return HTTPException(502, f"AI provider error: {str(e)[:300]}")

router = APIRouter(prefix="/api/chat", tags=["chat"])


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ShopRequest(BaseModel):
    customer_id: str | None = None       # demo login; a real app would take it from the auth session
    messages: list[Message]
    client_id: str = Field(default="", max_length=64)     # random id of this browser (memory owner)
    session_id: str | None = None


@router.get("/demo-users")
def demo_users():
    """A few real customer ids from the data: the most active retail customers and resellers."""
    rows = fetch_all("""
        (SELECT customer_key, customer_segment, governorate_ar, orders
         FROM gold.mart_customer_rfm WHERE customer_segment = 'Retail' AND orders > 0
         ORDER BY orders DESC LIMIT 4)
        UNION ALL
        (SELECT customer_key, customer_segment, governorate_ar, orders
         FROM gold.mart_customer_rfm WHERE customer_segment = 'B2B reseller' AND orders > 0
         ORDER BY orders DESC LIMIT 4)
    """)
    return rows


@router.post("/shop")
def shop_chat(req: ShopRequest):
    if not req.messages or req.messages[-1].role != "user":
        raise HTTPException(400, "The last message must come from the user")
    try:
        owner = memory.owner_key("shop", req.client_id, req.customer_id)
        result = shop_assistant.chat([m.model_dump() for m in req.messages], req.customer_id,
                                     memory.get_memory("shop", owner))
        result["session_id"] = _save(
            "shop", owner, req.session_id, req.messages[-1].content, result["reply"],
            {"products": result.get("products"), "tools": result.get("tools")})
        return result
    except Exception as e:                        # quota, bad key, provider down...
        raise _ai_error(e)


class ImageSearchRequest(BaseModel):
    image: str                            # data URL: "data:image/jpeg;base64,...."
    note: str | None = Field(default=None, max_length=300)   # optional text, e.g. "for kids"
    max_price: float | None = None


@router.post("/shop/image")
def shop_image_search(req: ImageSearchRequest):
    """Photo -> description (vision model) -> similar products (pgvector)."""
    try:
        return image_search.search_by_image(req.image, req.note, req.max_price)
    except image_search.ImageError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise _ai_error(e)


class AnalystRequest(BaseModel):
    messages: list[Message]
    client_id: str = Field(default="", max_length=64)
    session_id: str | None = None


@router.post("/analyst")
def analyst_chat(req: AnalystRequest):
    if not req.messages or req.messages[-1].role != "user":
        raise HTTPException(400, "The last message must come from the user")
    try:
        owner = memory.owner_key("analyst", req.client_id)
        result = analyst.chat([m.model_dump() for m in req.messages], memory.get_memory("analyst", owner))
        result["session_id"] = _save(
            "analyst", owner, req.session_id, req.messages[-1].content, result["reply"], {"result": result})
        return result
    except Exception as e:
        raise _ai_error(e)


# ---------------------------------------------------------------------------
# Memory endpoints
# ---------------------------------------------------------------------------
Assistant = Literal["shop", "analyst"]


@router.get("/session")
def get_session(assistant: Assistant, client_id: str = "", customer_id: str | None = None):
    owner = memory.owner_key(assistant, client_id, customer_id)
    return {"session": memory.current_session(assistant, owner),
            "memory": memory.get_memory(assistant, owner)}


class NewChatRequest(BaseModel):
    assistant: Assistant
    client_id: str = Field(default="", max_length=64)
    customer_id: str | None = None
    session_id: str | None = None


@router.post("/new")
def new_chat(req: NewChatRequest):
    owner = memory.owner_key(req.assistant, req.client_id, req.customer_id)
    return memory.new_chat(req.assistant, owner, req.session_id)


@router.delete("/memory")
def forget(assistant: Assistant, client_id: str = "", customer_id: str | None = None):
    memory.clear_memory(assistant, memory.owner_key(assistant, client_id, customer_id))
    return {"memory": ""}