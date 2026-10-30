# =============================================================================
# chat/shop_assistant.py  -  The customer & reseller chatbot (agent loop)
# -----------------------------------------------------------------------------
# How one answer is produced:
#   1. send: system prompt + conversation + the list of tools
#   2. the model either answers directly, or asks for one/more tool calls
#   3. we run those tools (safely, with the server-side customer id) and send
#      the results back
#   4. repeat until the model answers in text (max MAX_STEPS rounds)
# =============================================================================

import json

from ..db import fetch_one
from ..llm import chat_completion
from .memory import memory_prompt
from .shop_tools import CUSTOMER_TOOLS, TOOL_SPECS, TOOLS

MAX_STEPS = 5

SYSTEM_PROMPT = """You are "Cottonil Assistant", the shopping assistant of Cottonil, an Egyptian
cotton underwear and clothing brand. You help customers and resellers.

Rules:
- Reply in the customer's language. If they write Arabic, reply in friendly Egyptian Arabic.
- Use the tools for every fact (products, prices, sizes, branches, orders, policies).
  Never invent products, prices, order details or policies.
- Prices are in EGP. Mention sizes and the price range when you suggest products,
  and suggest 2-4 products at most.
- You can only see the logged-in customer's own orders. If a tool says login_required,
  ask the customer to log in. Never reveal anything about other customers, the company's
  sales, profits, costs, employees or suppliers - politely refuse such questions.
- You cannot place orders or change orders; for that, guide the customer to a branch or
  the website.
- Policy answers come from a demo knowledge base; say "according to our policy".
- Keep answers short and clear (a few lines, bullet points for product lists).
"""


def _customer_context(customer_id: str | None) -> str:
    if not customer_id:
        return "The user is a guest (not logged in)."
    c = fetch_one("""
        SELECT customer_key, customer_segment, governorate_ar FROM gold.dim_customer
        WHERE customer_key = %(c)s
    """, {"c": customer_id})
    if not c:
        return "The user is a guest (not logged in)."
    kind = "a reseller (B2B customer)" if c["customer_segment"] == "B2B reseller" else "a retail customer"
    return (f"The logged-in user is {kind}, customer id {c['customer_key']}, "
            f"living in {c['governorate_ar']}.")


def _run_tool(name: str, args: dict, customer_id: str | None):
    fn = TOOLS.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    args = {k: v for k, v in (args or {}).items() if k != "customer_id"}   # model can't choose the customer
    if name in CUSTOMER_TOOLS:
        args["customer_id"] = customer_id
    try:
        return fn(**args)
    except Exception as e:                                                  # never crash the chat
        return {"error": "tool_failed", "message": str(e)[:300]}


def chat(messages: list[dict], customer_id: str | None, memory: str = "") -> dict:
    """messages = [{"role": "user"|"assistant", "content": "..."}] (the visible chat)."""
    convo = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n" + _customer_context(customer_id) + memory_prompt(memory)},
        *[{"role": m["role"], "content": m["content"]} for m in messages[-12:]],   # last 12 turns
    ]
    used_tools, products = [], {}

    for _ in range(MAX_STEPS):
        resp = chat_completion(
            messages=convo, tools=TOOL_SPECS, temperature=0.3,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:                         # final answer
            return {"reply": msg.content or "", "tools": used_tools, "products": list(products.values())[:6]}

        # keep the model's tool request in the conversation, then add each result
        convo.append({
            "role": "assistant",
            "content": msg.content or "",
            # model_dump keeps EVERYTHING the model sent, including Gemini 3's
            # "thought_signature" (extra_content); Gemini 3 rejects the next turn
            # with error 400 if that signature is not sent back.
            "tool_calls": [tc.model_dump(exclude_none=True) for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _run_tool(tc.function.name, args, customer_id)
            used_tools.append({"name": tc.function.name,
                               "args": {k: v for k, v in args.items() if k != "customer_id"}})
            for p in result.get("products", []) if isinstance(result, dict) else []:
                products[p["product_id"]] = p           # product cards for the UI
            convo.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return {"reply": "Sorry, I could not finish that request. Please try rephrasing it.",
            "tools": used_tools, "products": list(products.values())[:6]}