"""
Simple Compare Tool for MMVN - aligned with DDV structure
Fetches product details then emits unified product-display JSON
Optimized for minimal token usage with ADK Context patterns.
"""

import logging
import json
import time
from typing import List
from google.adk.tools import ToolContext
from .context_optimized_tools import context_optimizer
from .session_state import set_conversation_context
from .artifact_tools import write_json_artifact, artifact_reference
from app.persistence_sqlite import save_comparison, save_artifact
from .session_state import get_last_user_question

logger = logging.getLogger(__name__)


def _safe_float(value, default=0.0):
    try:
        if isinstance(value, dict):
            for key in ["current", "final_price", "capacity", "value", "amount", "original"]:
                if key in value and isinstance(value[key], (int, float)):
                    return float(value[key])
            return default
        return float(value)
    except Exception:
        return default


def _to_minimal_product(product: dict) -> dict:
    images = product.get("media_gallery", []) or product.get("images", [])
    first_image = ""
    if isinstance(images, list) and images:
        first = images[0]
        first_image = first.get("url") if isinstance(first, dict) else first
    price_info = product.get("price_info") or product.get("price", {})
    current_price = (
        price_info.get("final_price")
        if isinstance(price_info, dict) and "final_price" in price_info
        else price_info.get("current", 0) if isinstance(price_info, dict) else 0
    )
    original_price = (
        price_info.get("regular_price") if isinstance(price_info, dict) else None
    )
    discount_percentage = 0
    if isinstance(price_info, dict):
        discount_percentage = price_info.get("discount_percentage", 0)

    return {
        "id": product.get("id", ""),
        "sku": product.get("sku", ""),
        "name": product.get("name", ""),
        "brand": product.get("brand") or product.get("manufacturer", ""),
        "category": product.get("category") or "",
        "price": {
            "current": current_price or 0,
            "original": original_price,
            "currency": "VND",
            "discount": f"{discount_percentage}%" if discount_percentage else None,
        },
        "image": {"url": first_image},
        "description": (
            product.get("short_description")
            or (product.get("description", {}) if isinstance(product.get("description"), dict) else product.get("description", ""))
            or ""
        ) if isinstance(product.get("short_description"), str) else (
            (product.get("description", {}).get("html", "") if isinstance(product.get("description"), dict) else product.get("description", ""))
        ),
        "productUrl": product.get("product_url") or product.get("url") or "",
        "availability": product.get("stock_status") or product.get("availability", "unknown"),
        "rating": {
            "average": (product.get("rating_summary") or {}).get("average", 0),
            "count": (product.get("rating_summary") or {}).get("count", 0),
        },
        "specs": product.get("specs") or {},
        "colors": product.get("colors", []),
        "storage_options": product.get("storage_options", []),
        "promotions": product.get("promotions", {}),
    }


async def compare_products(product_ids: List[str], tool_context: ToolContext) -> str:
    start_time = time.time()
    try:
        # Log tool usage
        log_entry = {
            "timestamp": start_time,
            "tool": "compare_products",
            "input": {
                "product_ids": product_ids,
                "product_count": len(product_ids)
            }
        }
        logger.info(f"TOOL_USAGE: {json.dumps(log_entry, ensure_ascii=False)}")
        
        if len(product_ids) < 2:
            return "Cần ít nhất 2 sản phẩm để so sánh"
        if len(product_ids) > 5:
            return "Chỉ có thể so sánh tối đa 5 sản phẩm cùng lúc"

        from app.tools.cng.product_tools import get_product_detail as cng_get

        products_full = []
        for pid in product_ids:
            result = await cng_get(product_id=pid, tool_context=tool_context)
            if result.get("status") == "success" and result.get("product"):
                products_full.append(result["product"]) 

        if len(products_full) < 2:
            return "Không tìm đủ sản phẩm để so sánh"

        minimal_products = [_to_minimal_product(p) for p in products_full]

        # Use context optimizer for minimal response
        compare_data = {
            "products": minimal_products
        }
        
        # Optimize response using context optimizer
        json_response = context_optimizer.optimize_compare_response(compare_data, f"compare {len(product_ids)} products")

        # Store brief conversation context
        try:
            set_conversation_context(tool_context.state, {
                "last_action": "compare",
                "num_products": len(product_ids)
            })
        except Exception:
            pass

        # Persist artifact: comparison results
        try:
            session_id = str(getattr(getattr(tool_context, 'session', None), 'id', 'unknown'))
            compare_payload = {
                "type": "comparison",
                "product_ids": product_ids,
                "products": minimal_products,
                "intent": "compare",
                "selected_answer": None,
                "user_question": get_last_user_question(tool_context.state),
                "created_at": time.time(),
            }
            path = write_json_artifact(compare_payload, category="compare", session_id=session_id)
            from .session_state import add_artifact_ref
            add_artifact_ref(tool_context.state, "compare", artifact_reference(path))
            try:
                save_artifact(session_id, "compare", path)
                save_comparison(session_id, product_ids, minimal_products)
            except Exception:
                pass
        except Exception:
            pass

        # Log tool completion
        end_time = time.time()
        log_entry = {
            "timestamp": end_time,
            "tool": "compare_products",
            "output": {
                "products_compared": len(products_full),
                "processing_time": end_time - start_time
            }
        }
        logger.info(f"TOOL_COMPLETION: {json.dumps(log_entry, ensure_ascii=False)}")
        
        return json_response
    except Exception as e:
        end_time = time.time()
        logger.exception("Compare error")
        
        # Log tool error
        log_entry = {
            "timestamp": end_time,
            "tool": "compare_products",
            "error": str(e),
            "processing_time": end_time - start_time
        }
        logger.error(f"TOOL_ERROR: {json.dumps(log_entry, ensure_ascii=False)}")
        
        return f"Lỗi khi so sánh sản phẩm: {str(e)}"


