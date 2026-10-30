# =============================================================================
# fetch_product_images.py  -  Get one photo per product from the public website
# -----------------------------------------------------------------------------
# The catalog already has each product's page URL (source_url) on
# cottonilegypt.com. The site runs on Shopify, and every Shopify product page
# also exists as JSON: just add ".json" to the URL. That JSON lists the product
# photos, so we take the first one and save its link (not the image file)
# in ai.product_images. The chatbot then shows the photo on its product cards.
#
# Polite scraping: one request at a time with a short pause, and only the
# products that are in our catalog. Used for the demo only.
#
# Usage (project folder, venv active, internet needed):
#     python ai/fetch_product_images.py
# Re-running it only fetches products that don't have a photo yet.
# =============================================================================

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PAUSE_SECONDS = 0.7
HEADERS = {"User-Agent": "Mozilla/5.0 (HVIA student project - catalog demo)"}


def product_json_url(page_url: str) -> str | None:
    """https://site/products/handle?x=1  ->  https://site/products/handle.json"""
    if not page_url or "/products/" not in page_url:
        return None
    parts = urllib.parse.urlsplit(page_url.strip())
    path = parts.path.rstrip("/")
    return urllib.parse.urlunsplit((parts.scheme or "https", parts.netloc, path + ".json", "", ""))


def first_image(json_url: str) -> str | None:
    req = urllib.request.Request(json_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        product = json.loads(resp.read().decode("utf-8"))["product"]
    img = (product.get("image") or {}).get("src") or next(
        (i.get("src") for i in product.get("images", []) if i.get("src")), None)
    if img and img.startswith("//"):
        img = "https:" + img
    if img:                                     # ask Shopify's CDN for a small version (faster cards)
        img += ("&" if "?" in img else "?") + "width=400"
    return img


def main():
    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"), port=int(os.getenv("POSTGRES_PORT", "5435")),
        dbname=os.getenv("POSTGRES_DB"), user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"), autocommit=True,
    ) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS ai")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai.product_images (
                product_id TEXT PRIMARY KEY,
                image_url  TEXT NOT NULL,
                fetched_at TIMESTAMPTZ DEFAULT now()
            )""")
        products = conn.execute("""
            SELECT p.product_id, MIN(p.source_url) AS url
            FROM gold.dim_product p
            WHERE p.source_url IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM ai.product_images i WHERE i.product_id = p.product_id)
            GROUP BY p.product_id ORDER BY p.product_id
        """).fetchall()
        print(f"Products without a photo yet: {len(products)}")

        ok = failed = 0
        for n, (product_id, url) in enumerate(products, start=1):
            json_url = product_json_url(url)
            try:
                img = first_image(json_url) if json_url else None
            except Exception as e:                       # page removed, no internet, etc.
                img = None
                print(f"   {product_id}: failed ({str(e)[:80]})")
            if img:
                conn.execute("""INSERT INTO ai.product_images (product_id, image_url) VALUES (%s, %s)
                                ON CONFLICT (product_id) DO UPDATE SET image_url = EXCLUDED.image_url""",
                             (product_id, img))
                ok += 1
            else:
                failed += 1
            if n % 20 == 0:
                print(f"   {n}/{len(products)} done")
            time.sleep(PAUSE_SECONDS)

        total = conn.execute("SELECT COUNT(*) FROM ai.product_images").fetchone()[0]
        print(f"\nDone: {ok} new photos, {failed} without photo. Products with a photo: {total}.")
        print("Restart the backend, then ask the Shopping Assistant for a product.")


if __name__ == "__main__":
    main()