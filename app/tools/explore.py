"""
Simple Explore Tool for MMVN - direct GraphQL to online.mmvietnam.com
"""

import logging
import json
import time
from typing import Dict, Any, List
from google.adk.tools import ToolContext
import aiohttp
import urllib.parse

logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://online.mmvietnam.com/graphql"
DEFAULT_STORE = "b2c_10010_vi"


def _build_product_url(product: Dict[str, Any]) -> str:
    if product.get("url_key") and product.get("url_suffix"):
        return f"https://online.mmvietnam.com/product/{product['url_key']}{product['url_suffix']}"
    if product.get("url_key"):
        return f"https://online.mmvietnam.com/product/{product['url_key']}.html"
    if product.get("url_path"):
        return f"https://online.mmvietnam.com{product['url_path']}"
    return ""


def _to_minimal_product(product: Dict[str, Any]) -> Dict[str, Any]:
    image_url = product.get("small_image", {}).get("url", "") if isinstance(product.get("small_image"), dict) else ""
    current_price = 0
    original_price = None
    discount_percentage = None
    try:
        max_price = product.get("price_range", {}).get("maximum_price", {})
        final_price = max_price.get("final_price", {})
        current_price = final_price.get("value", 0)
        regular_amount = product.get("price", {}).get("regularPrice", {}).get("amount", {})
        original_price = regular_amount.get("value")
        percent_off = max_price.get("discount", {}).get("percent_off")
        if isinstance(percent_off, (int, float)) and percent_off > 0:
            discount_percentage = f"{round(percent_off)}%"
    except Exception:
        pass

    description = ""
    if isinstance(product.get("description"), dict):
        description = product.get("description", {}).get("html", "")
    elif isinstance(product.get("description"), str):
        description = product.get("description", "")

    minimal: Dict[str, Any] = {
        "id": product.get("id", ""),
        "sku": product.get("sku", ""),
        "name": product.get("name", ""),
        "price": {
            "current": current_price or 0,
            "original": original_price,
            "currency": "VND",
            "discount": discount_percentage,
        },
        "image": {"url": image_url},
        "description": description,
        "productUrl": _build_product_url(product),
    }
    if product.get("unit_ecom"):
        minimal["unit"] = product.get("unit_ecom")
    return minimal


async def _graphql_get(session: aiohttp.ClientSession, query: str) -> Dict[str, Any]:
    params = {"query": query}
    url = GRAPHQL_ENDPOINT + "?" + urllib.parse.urlencode(params)
    headers = {"Store": DEFAULT_STORE}
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        resp.raise_for_status()
        return await resp.json()


async def explore_product(product_id: str, tool_context: ToolContext) -> str:
    start_time = time.time()
    try:
        # Log tool usage
        log_entry = {
            "timestamp": start_time,
            "tool": "explore_product",
            "input": {
                "product_id": product_id
            }
        }
        logger.info(f"TOOL_USAGE: {json.dumps(log_entry, ensure_ascii=False)}")
        
        # Support multiple SKUs separated by comma/space; fallback to single
        raw = (product_id or "").strip()
        sku_list: List[str] = [s.strip() for s in raw.replace("\n", ",").replace(";", ",").split(",") if s.strip()]
        sku_list = sku_list[:12] if sku_list else []

        if len(sku_list) <= 1:
            safe_id = (sku_list[0] if sku_list else raw).replace('"', '\\"')
            gql = (
                "query { products(filter: { sku: { eq: \"%s\" } }, pageSize: 1, currentPage: 1) { items { "
                "id sku name url_key url_suffix url_path "
                "price { regularPrice { amount { currency value } } } "
                "price_range { maximum_price { final_price { currency value } discount { percent_off } } } "
                "small_image { url } unit_ecom description { html } } } }"
            ) % safe_id
        else:
            # Batch fetch with IN filter
            # Quote each SKU safely for GraphQL IN list
            safe_list = ", ".join([json.dumps(s) for s in sku_list])
            gql = (
                "query { products(filter: { sku: { in: [%s] } }, pageSize: %d, currentPage: 1) { items { "
                "id sku name url_key url_suffix url_path "
                "price { regularPrice { amount { currency value } } } "
                "price_range { maximum_price { final_price { currency value } discount { percent_off } } } "
                "small_image { url } unit_ecom description { html } } } }"
            ) % (safe_list, max(1, len(sku_list)))

        async with aiohttp.ClientSession() as session:
            data = await _graphql_get(session, gql)

        items = data.get("data", {}).get("products", {}).get("items", [])
        if not items:
            return json.dumps({
                "type": "product-display",
                "message": "Không tìm thấy sản phẩm theo yêu cầu",
                "products": []
            }, ensure_ascii=False)

        minimals = [_to_minimal_product(p) for p in items]
        json_response = {
            "type": "product-display",
            "message": ("Chi tiết sản phẩm" if len(minimals) == 1 else "Danh sách sản phẩm đã chọn"),
            "products": minimals,
        }
        # Log tool completion
        end_time = time.time()
        log_entry = {
            "timestamp": end_time,
            "tool": "explore_product",
            "output": {
                "product_found": bool(items),
                "count": len(items),
                "processing_time": end_time - start_time
            }
        }
        logger.info(f"TOOL_COMPLETION: {json.dumps(log_entry, ensure_ascii=False)}")
        
        return json.dumps(json_response, ensure_ascii=False)
    except Exception as e:
        end_time = time.time()
        logger.exception("Explore error")
        
        # Log tool error
        log_entry = {
            "timestamp": end_time,
            "tool": "explore_product",
            "error": str(e),
            "processing_time": end_time - start_time
        }
        logger.error(f"TOOL_ERROR: {json.dumps(log_entry, ensure_ascii=False)}")
        
        return f"Lỗi khi lấy thông tin sản phẩm: {str(e)}"


