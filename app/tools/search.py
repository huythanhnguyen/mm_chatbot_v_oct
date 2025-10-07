"""
Antsomi CDP 365 API Smart Search Tool for MMVN
Uses the new Antsomi search engine for better product discovery.
Optimized for minimal token usage with ADK Context patterns.
"""

import logging
import json
import time
from typing import Optional, Dict, Any, List
import unicodedata
from google.adk.tools import ToolContext
import aiohttp
import urllib.parse
from .context_optimized_tools import context_optimizer
from .session_state import (
    set_current_search,
    get_current_search,
    set_pagination,
    get_pagination,
    get_last_user_question,
)
from .artifact_tools import write_json_artifact, artifact_reference
from app.persistence_sqlite import save_search, save_artifact

logger = logging.getLogger(__name__)

# Antsomi CDP 365 API Configuration
ANTISOMI_BASE_URL = "https://search.ants.tech"
ANTISOMI_BEARER_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJwb3J0YWxJZCI6IjU2NDg5MjM3MyIsIm5hbWUiOiJNZWdhIE1hcmtldCJ9.iXymLjrJn-QVPO6gOV3MW8zJ4-u0Ih2L4qSOBZdIM24"
DEFAULT_USER_ID = "564996752"  # Default user ID for testing
DEFAULT_STORE_ID = "10010"
DEFAULT_PRODUCT_TYPE = "B2C"


def _to_minimal_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Antsomi API product response to minimal format expected by frontend."""
    # Extract price information
    current_price = 0
    original_price = None
    discount_percentage = None
    
    try:
        price_str = str(product.get("price", "0"))
        original_price_str = str(product.get("original_price", "0"))
        
        current_price = float(price_str) if price_str.replace(".", "").isdigit() else 0
        original_price = float(original_price_str) if original_price_str.replace(".", "").isdigit() else None
        
        # Calculate discount if original price is higher
        if original_price and original_price > current_price:
            discount_amount = original_price - current_price
            discount_percentage = f"{round((discount_amount / original_price) * 100)}%"
    except Exception:
        pass

    # Build product URL from page_url field
    product_url = product.get("page_url", "")
    
    # Extract image URL
    image_url = product.get("image_url", "")

    # Build minimal product object
    minimal: Dict[str, Any] = {
        "id": product.get("id", ""),
        "sku": product.get("sku", ""),
        "name": product.get("title", ""),
        "price": {
            "current": current_price,
            "original": original_price,
            "currency": "VND",
            "discount": discount_percentage,
        },
        "image": {"url": image_url},
        "description": "",  # Antsomi API doesn't provide description
        "productUrl": product_url,
        "category": product.get("category", ""),
        "status": product.get("status", ""),
    }
    
    return minimal




async def _antsomi_request(session: aiohttp.ClientSession, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Make request to Antsomi API with proper authentication."""
    url = f"{ANTISOMI_BASE_URL}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {ANTISOMI_BEARER_TOKEN}",
        "Content-Type": "application/json",
        "Accept-Language": "vi",
    }
    
    logger.info(f"[Antsomi] GET {url} params={json.dumps(params, ensure_ascii=False)}")
    async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        text = await resp.text()
        try:
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[Antsomi] HTTP {resp.status} body={text[:500]}")
            raise
        try:
            data = json.loads(text)
        except Exception:
            logger.error(f"[Antsomi] Non-JSON response body prefix: {text[:200]}")
            data = {"raw": text}
        logger.info(f"[Antsomi] OK {endpoint} keys={list(data.keys())}")
        return data


async def suggest_keywords(query: str, user_id: str = DEFAULT_USER_ID) -> List[str]:
    """Get keyword suggestions from Antsomi API."""
    try:
        params = {
            "q": query,
            "user_id": user_id,
            "store_id": DEFAULT_STORE_ID,
            "product_type": DEFAULT_PRODUCT_TYPE
        }
        
        async with aiohttp.ClientSession() as session:
            data = await _antsomi_request(session, "suggest", params)
        
        suggestions = data.get("suggestions", [])
        return [s.get("keyword", "") for s in suggestions if s.get("keyword")]
    except Exception as e:
        logger.warning(f"Failed to get keyword suggestions: {e}")
        return []


async def search_products_antsomi(query: str, user_id: str = DEFAULT_USER_ID, 
                                 filters: Optional[Dict[str, Any]] = None,
                                 page: int = 1, limit: int = 20) -> Dict[str, Any]:
    """Search products using Antsomi Smart Search API."""
    try:
        params = {
            "q": query,
            "user_id": user_id,
            "store_id": DEFAULT_STORE_ID,
            "product_type": DEFAULT_PRODUCT_TYPE,
            "page": page,
            "limit": limit
        }
        
        # Add filters if provided
        if filters:
            params["filters"] = json.dumps(filters)
        
        async with aiohttp.ClientSession() as session:
            data = await _antsomi_request(session, "smart_search", params)
            # Fallback 1: if no results-like keys, try using 'query' instead of 'q'
            if not any(k in data for k in ("results", "items", "data")):
                alt_params = dict(params)
                alt_params.pop("q", None)
                alt_params["query"] = query
                try:
                    data_alt = await _antsomi_request(session, "smart_search", alt_params)
                    if any(k in data_alt for k in ("results", "items", "data")):
                        data = data_alt
                except Exception:
                    pass
            # Fallback 2: try a different endpoint name 'search'
            if not any(k in data for k in ("results", "items", "data")):
                try:
                    data_search = await _antsomi_request(session, "search", params)
                    data = data_search
                except Exception:
                    pass
        
        return data
    except Exception as e:
        logger.error(f"Antsomi search failed: {e}")
        return {"results": [], "total": "0", "type": "", "categories": {}}


async def search_products(keywords: Optional[str] = None, tool_context: ToolContext = None, filters_json: Optional[str] = None, page: Optional[int] = None) -> str:
    """Main search function using Antsomi CDP 365 API Smart Search."""
    start_time = time.time()
    try:
        # Manage pagination state in ToolContext.state
        # Normalize and backfill missing inputs from state when possible

        # Ensure tool_context is usable
        if tool_context is None:
            # Create a minimal stand-in to avoid attribute errors
            class _Dummy:
                state: Dict[str, Any] = {}
            tool_context = _Dummy()  # type: ignore

        # Parse filters from JSON string if provided
        filters: Optional[Dict[str, Any]] = None
        if isinstance(filters_json, str) and filters_json.strip():
            try:
                filters = json.loads(filters_json)
                if not isinstance(filters, dict):
                    filters = None
            except Exception:
                filters = None  # invalid json → treat as no filters

        state_key = "antsomi.search_state"
        # Backfill keywords from session_state first, then legacy keys
        if not keywords or (isinstance(keywords, str) and not keywords.strip()):
            try:
                prev = getattr(tool_context, 'state', {}) or {}
                if isinstance(prev, dict):
                    # session_state current_search
                    cs = get_current_search(prev)
                    if isinstance(cs, dict) and cs.get('keywords'):
                        keywords = cs.get('keywords')
                        if not filters:
                            filters = cs.get('filters') or None
                    # legacy
                    if (not keywords) and isinstance(prev.get(state_key), dict) and prev[state_key].get('keywords'):
                        keywords = prev[state_key]['keywords']
                    elif isinstance(prev.get('latest_search'), str):
                        try:
                            latest = json.loads(prev['latest_search'])
                            if isinstance(latest, dict) and latest.get('query'):
                                keywords = latest['query']
                        except Exception:
                            pass
            except Exception:
                pass
        # Final guard: if still missing, return a user-friendly message instead of failing
        if not keywords or not str(keywords).strip():
            return json.dumps({
                "type": "product-display",
                "message": "Không có từ khóa tìm kiếm. Vui lòng nhập từ khóa (ví dụ: 'sữa tươi').",
                "products": []
            }, ensure_ascii=False)
        # If page is not specified or invalid, pull from session pagination or default to 1
        try:
            if page is not None:
                page = int(page)
            else:
                pagination = get_pagination(tool_context.state)
                page = int(pagination.get("page", 1))
        except Exception:
            page = 1
        if page <= 0:
            page = 1

        if hasattr(tool_context, 'state'):
            # persist to both structured session and legacy key for backward compat
            set_current_search(tool_context.state, keywords=keywords, filters=filters)
            set_pagination(tool_context.state, page=page)
            tool_context.state[state_key] = {
                'keywords': keywords,
                'filters': filters,
                'page': page,
                'ts': time.time(),
            }

        logger.info("[Antsomi] Smart search: %s (page: %d)", keywords, page)
        
        # Log tool usage
        log_entry = {
            "timestamp": time.time(),
            "tool": "search_products",
            "input": {
                "keywords": keywords,
                "filters": filters,
                "page": page
            }
        }
        logger.info(f"TOOL_USAGE: {json.dumps(log_entry, ensure_ascii=False)}")
        
        # Keep original keywords with Vietnamese accents - no accent stripping
        search_query = keywords
        
        # Search products using Antsomi API with default limit of 20
        search_result = await search_products_antsomi(search_query, filters=filters, page=page, limit=20)
        
        # Handle multiple possible response shapes
        results = search_result.get("results")
        if results is None and isinstance(search_result.get("data"), dict):
            results = search_result.get("data", {}).get("results", [])
        if results is None and isinstance(search_result.get("items"), list):
            results = search_result.get("items", [])
        results = results or []

        total = search_result.get("total")
        if total is None and isinstance(search_result.get("data"), dict):
            total = search_result.get("data", {}).get("total")
        total = str(total) if total is not None else "0"

        search_type = search_result.get("type", "")
        categories = search_result.get("categories", {})
        
        # Convert to minimal product format
        minimal_products = [_to_minimal_product(p) for p in results]
        
        # Sort by category name (empty last), then by product name
        minimal_products.sort(key=lambda x: ((x.get("category") or "") == "", (x.get("category") or ""), x.get("name") or ""))
        
        # Use context optimizer for minimal response
        search_data = {
            "products": minimal_products,
            "search_metadata": {
                "total": total,
                "search_type": search_type,
                "categories": categories,
                "pagination": {
                    "current_page": page,
                    "total_pages": (int(total) + 19) // 20 if total != "0" else 1,
                    "items_per_page": 20,
                    "has_next_page": page < ((int(total) + 19) // 20 if total != "0" else 1),
                    "has_prev_page": page > 1
                }
            }
        }
        
        # Optimize response using context optimizer
        json_response = context_optimizer.optimize_search_response(search_data, keywords)
        
        # If no results, log payload and try suggest->requery or simplified variants (keep Vietnamese accents)
        if not minimal_products:
            try:
                logger.info(f"[Antsomi] Empty results payload keys={list(search_result.keys())} sample={json.dumps({k: search_result[k] for k in list(search_result)[:3]}, ensure_ascii=False)[:400]}")
            except Exception:
                pass
            # 0) Try suggest API to get a close keyword
            try:
                suggestions = await suggest_keywords(keywords)
            except Exception:
                suggestions = []
            fallback_queries = []
            if suggestions:
                fallback_queries.append(suggestions[0])

            # 1) Keep only first two words
            words = keywords.split()
            if len(words) > 2:
                fallback_queries.append(' '.join(words[:2]))

            # 2) Single first word
            if words:
                fallback_queries.append(words[0])

            # Deduplicate fallback queries while preserving order
            seen = set()
            unique_fallbacks = []
            for fq in fallback_queries:
                if fq and fq not in seen:
                    unique_fallbacks.append(fq)
                    seen.add(fq)

            # Try fallback queries
            for fallback_query in unique_fallbacks:
                logger.info(f"Trying fallback search: {fallback_query}")
                fallback_result = await search_products_antsomi(fallback_query, filters=None, page=page, limit=20)
                fb_results = fallback_result.get("results") or fallback_result.get("data", {}).get("results", []) or fallback_result.get("items", []) or []
                if fb_results:
                    minimal_products = [_to_minimal_product(p) for p in fb_results]
                    minimal_products.sort(key=lambda x: ((x.get("category") or "") == "", (x.get("category") or ""), x.get("name") or ""))
                    fallback_data = {
                        "products": minimal_products,
                        "search_metadata": {
                            "total": fallback_result.get("total", "0"),
                            "search_type": fallback_result.get("type", ""),
                            "categories": fallback_result.get("categories", {})
                        }
                    }
                    json_response = context_optimizer.optimize_search_response(fallback_data, fallback_query)
                    break
        
        # Persist artifacts: search history + important products (top 10-20)
        try:
            session_id = str(getattr(getattr(tool_context, 'session', None), 'id', 'unknown'))
            important_products = minimal_products[:20]
            search_artifact_payload = {
                "type": "search_history",
                "query": keywords,
                "filters": filters or {},
                "page": page,
                "intent": getattr(getattr(tool_context, 'state', {}), 'get', lambda *_: {})('mmvn_session', {}).get('context', {}).get('intent', ''),
                "selected_answer": None,
                "user_question": get_last_user_question(tool_context.state),
                "metadata": {
                    "total": total,
                    "search_type": search_type,
                    "categories": categories,
                },
                "important_products": important_products,
                "raw_count": len(results),
                "created_at": time.time(),
            }
            path = write_json_artifact(search_artifact_payload, category="search", session_id=session_id)
            from .session_state import add_artifact_ref
            add_artifact_ref(tool_context.state, "search", artifact_reference(path))
            try:
                save_artifact(session_id, "search", path, meta={"query": keywords})
                save_search(session_id, keywords, filters or {}, page=page, total=total, search_type=search_type, categories=categories, top_products=important_products)
            except Exception:
                pass
        except Exception:
            pass

        # Log tool completion
        end_time = time.time()
        log_entry = {
            "timestamp": end_time,
            "tool": "search_products",
            "output": {
                "products_found": len(minimal_products),
                "total_results": total,
                "search_type": search_type,
                "processing_time": end_time - start_time
            }
        }
        logger.info(f"TOOL_COMPLETION: {json.dumps(log_entry, ensure_ascii=False)}")
        
        return json_response
        
    except Exception as e:
        end_time = time.time()
        logger.exception("Antsomi search error")
        
        # Log tool error
        log_entry = {
            "timestamp": end_time,
            "tool": "search_products",
            "error": str(e),
            "processing_time": end_time - start_time
        }
        logger.error(f"TOOL_ERROR: {json.dumps(log_entry, ensure_ascii=False)}")
        
        return f"Lỗi khi tìm kiếm sản phẩm: {str(e)}"


