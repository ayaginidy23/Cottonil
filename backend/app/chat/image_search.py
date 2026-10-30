# =============================================================================
# chat/image_search.py  -  "Photo -> similar products" for the shopping assistant
# -----------------------------------------------------------------------------
# Two steps:
#   1. a vision model (Gemini) LOOKS at the customer's photo and writes a short
#      product description, e.g. "men's white cotton crew-neck t-shirt"
#   2. that description goes through the SAME semantic search as typed questions
#      (embedding + pgvector), so the photo is matched to the real catalog
# The photo is only sent to the model for this one request; it is never stored.
# =============================================================================

import re

from ..llm import chat_completion
from .shop_tools import search_products

MAX_IMAGE_CHARS = 6_000_000            # ~4.5 MB image after base64; the UI resizes before sending
DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=]+$")

VISION_PROMPT = """You help an Egyptian cotton clothing store (underwear, t-shirts, pyjamas,
socks, kids wear, home wear) find products similar to a customer's photo.
Describe ONLY the main garment in the photo as a short search phrase in English:
garment type, who it is for (men / women / kids / baby), colour, and material or style
if visible. Example: "men's white cotton crew-neck t-shirt".
If the photo shows no clothing, reply exactly: NOT_CLOTHING
Reply with the phrase only, no extra words."""


class ImageError(ValueError):
    """Bad input from the user (shown as a 400 error)."""


def describe_image(data_url: str) -> str:
    resp = chat_completion(
        messages=[{"role": "user", "content": [
            {"type": "text", "text": VISION_PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
        temperature=0.1,
    )
    return (resp.choices[0].message.content or "").strip().strip('"').strip()


def search_by_image(data_url: str, note: str | None = None, max_price: float | None = None) -> dict:
    if len(data_url) > MAX_IMAGE_CHARS:
        raise ImageError("The image is too large - please use a smaller photo.")
    if not DATA_URL_RE.match(data_url):
        raise ImageError("Please upload a PNG, JPG or WEBP image.")

    description = describe_image(data_url)
    if not description or "NOT_CLOTHING" in description.upper():
        return {"description": None, "products": [],
                "reply": "مش قادر ألاقي قطعة لبس واضحة في الصورة 🙏 جرّب صورة تانية للمنتج لوحده."}

    query = f"{description}. {note}" if note else description        # optional text from the user
    result = search_products(query=query, max_price=max_price)
    products = result.get("products", [])
    if products:
        reply = f"شُفت في الصورة: {description}\nدي أقرب منتجات عندنا ليها 👇"
    else:
        reply = f"شُفت في الصورة: {description}\nللأسف مالقيتش منتج قريب منها في الكتالوج."
    return {"description": description, "products": products, "reply": reply}