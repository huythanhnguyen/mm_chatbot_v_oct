"""
Context-Optimized Tools - Tối ưu hóa tool outputs theo ADK Context patterns
Dựa trên: https://google.github.io/adk-docs/context/#accessing-information
"""

import logging
import json
import time
from typing import Dict, Any, Optional, List
from google.genai import types as genai_types
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

def estimate_tokens(text: str) -> int:
    """Estimate token count for text (optimized for Vietnamese)"""
    if not text:
        return 0
    return max(1, len(text) // 3.7)

class ContextOptimizedToolWrapper:
    """
    Wrapper để tối ưu hóa tool outputs theo ADK Context patterns.
    
    Key optimizations:
    1. Minimal response format
    2. Token-aware output filtering
    3. Context-aware data selection
    4. Smart summarization
    """
    
    def __init__(self, max_output_tokens: int = 500):
        self.max_output_tokens = max_output_tokens

    # --------------------------- Context filtering (pre-LLM) ---------------------------
    def filter_llm_request_contents(
        self,
        contents: List[genai_types.Content],
        *,
        num_invocations_to_keep: int = 5,
        token_budget: int = 3000,
        max_part_chars: int = 2000,
    ) -> List[genai_types.Content]:
        """
        Trim context before sending to LLM, inspired by ADK ContextFilterPlugin.

        - Keep only last N invocations (user.. -> model)
        - Enforce token budget by truncating earliest kept texts
        - Drop non-text parts silently; keep text parts only
        - Truncate very long text parts to max_part_chars
        """
        logger.info(
            f"[ContextFilter] start contents={len(contents)} keep={num_invocations_to_keep} "
            f"budget={token_budget} max_part_chars={max_part_chars}"
        )
        if not contents:
            return contents

        # 1) Keep only last N invocations
        invocations: List[List[genai_types.Content]] = []
        current_invocation: List[genai_types.Content] = []
        for c in contents:
            current_invocation.append(c)
            if c.role == 'model':
                invocations.append(current_invocation)
                current_invocation = []
        # If the last turn didn't include a model response, treat as ongoing invocation
        if current_invocation:
            invocations.append(current_invocation)

        kept_invocations = invocations[-num_invocations_to_keep:] if num_invocations_to_keep > 0 else invocations
        kept: List[genai_types.Content] = [c for inv in kept_invocations for c in inv]
        logger.info(
            f"[ContextFilter] invocations total={len(invocations)} kept={len(kept_invocations)} flat_contents={len(kept)}"
        )

        # 2) Drop non-text parts and truncate long parts
        def _shrink_content(c: genai_types.Content) -> genai_types.Content:
            new_parts: List[genai_types.Part] = []
            for p in c.parts or []:
                txt = getattr(p, 'text', None)
                if txt is None:
                    # skip non-text parts to reduce context size
                    continue
                if len(txt) > max_part_chars:
                    txt = txt[:max_part_chars] + '…'
                new_parts.append(genai_types.Part(text=txt))
            return genai_types.Content(role=c.role, parts=new_parts)

        shrunk = [_shrink_content(c) for c in kept]
        shrunk_parts = sum(len(c.parts or []) for c in shrunk)
        logger.info(f"[ContextFilter] after shrink: contents={len(shrunk)} parts={shrunk_parts}")

        # 3) Enforce token budget (rough estimate)
        def _contents_tokens(cs: List[genai_types.Content]) -> int:
            total = 0
            for c in cs:
                for p in c.parts or []:
                    if p.text:
                        total += estimate_tokens(p.text)
            return total

        total_tokens = _contents_tokens(shrunk)
        if total_tokens <= token_budget:
            logger.info(f"[ContextFilter] kept={len(shrunk)} contents, tokens≈{total_tokens}")
            return shrunk

        # Remove from the oldest side until within budget
        pruned = list(shrunk)
        while pruned and _contents_tokens(pruned) > token_budget:
            pruned.pop(0)
        logger.info(f"[ContextFilter] pruned to {len(pruned)} contents, tokens≈{_contents_tokens(pruned)}")
        return pruned
    
    def optimize_search_response(self, search_data: Dict[str, Any], user_query: str) -> str:
        """
        Optimize search response để minimize tokens while keeping essential info.
        """
        try:
            products = search_data.get("products", [])
            total = search_data.get("search_metadata", {}).get("total", "0")
            search_type = search_data.get("search_metadata", {}).get("search_type", "")
            
            # Create ultra-minimal response
            if not products:
                return json.dumps({
                    "type": "no-results",
                    "message": f"Không tìm thấy sản phẩm phù hợp với '{user_query}'"
                }, ensure_ascii=False)
            
            # Select essential products (max 10 for better user experience)
            essential_products = self._select_essential_products(products, user_query, max_products=10)
            
            # Create minimal response
            response = {
                "type": "product-display",
                "message": f"Tìm thấy {len(essential_products)} sản phẩm phù hợp",
                "products": essential_products,
                "metadata": {
                    "total": total,
                    "type": search_type,
                    "showing": len(essential_products)
                }
            }
            
            # Convert to JSON and check token count
            json_response = json.dumps(response, ensure_ascii=False)
            token_count = estimate_tokens(json_response)
            
            # If still too large, further reduce
            if token_count > self.max_output_tokens:
                response = self._further_reduce_response(response, user_query)
                json_response = json.dumps(response, ensure_ascii=False)
            
            logger.info(f"Search response optimized: {token_count} tokens")
            return json_response
            
        except Exception as e:
            logger.error(f"Error optimizing search response: {e}")
            return json.dumps({
                "type": "error",
                "message": f"Lỗi khi tìm kiếm: {str(e)}"
            }, ensure_ascii=False)
    
    def _select_essential_products(self, products: List[Dict[str, Any]], user_query: str, max_products: int = 6) -> List[Dict[str, Any]]:
        """
        Select only essential products based on relevance and token efficiency.
        """
        if not products:
            return []
        
        # Score products by relevance
        scored_products = []
        for product in products:
            score = self._calculate_product_relevance(product, user_query)
            scored_products.append((product, score))
        
        # Sort by relevance (highest first)
        scored_products.sort(key=lambda x: x[1], reverse=True)
        
        # Select top products and convert to minimal format
        essential_products = []
        for product, score in scored_products[:max_products]:
            minimal_product = self._create_minimal_product(product)
            essential_products.append(minimal_product)
        
        return essential_products
    
    def _calculate_product_relevance(self, product: Dict[str, Any], user_query: str) -> float:
        """
        Calculate relevance score for product based on user query.
        """
        if not product or not user_query:
            return 0.0
        
        score = 0.0
        query_lower = user_query.lower()
        
        # Check product name
        product_name = product.get("name", "").lower()
        if product_name:
            # Exact match gets highest score
            if query_lower in product_name:
                score += 1.0
            # Word match gets medium score
            elif any(word in product_name for word in query_lower.split()):
                score += 0.5
        
        # Check category
        category = product.get("category", "").lower()
        if category and any(word in category for word in query_lower.split()):
            score += 0.3
        
        # Check SKU
        sku = product.get("sku", "").lower()
        if sku and query_lower in sku:
            score += 0.8
        
        return score
    
    def _create_minimal_product(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create minimal product object with only essential fields.
        """
        return {
            "id": product.get("id", ""),
            "name": product.get("name", ""),
            "price": {
                "current": product.get("price", {}).get("current", 0),
                "currency": "VND"
            },
            "image": {"url": product.get("image", {}).get("url", "")},
            "productUrl": product.get("productUrl", ""),
            "category": product.get("category", "")
        }
    
    def _further_reduce_response(self, response: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        """
        Further reduce response if still too large.
        """
        # Reduce products to top 10 if still too large
        if "products" in response and len(response["products"]) > 10:
            response["products"] = response["products"][:10]
            response["message"] = f"Tìm thấy {len(response['products'])} sản phẩm phù hợp (hiển thị top 10)"
        
        # Remove non-essential fields
        for product in response.get("products", []):
            if "category" in product:
                del product["category"]
            if "image" in product and not product["image"].get("url"):
                del product["image"]
        
        return response
    
    def optimize_compare_response(self, compare_data: Dict[str, Any], user_query: str) -> str:
        """
        Optimize compare response để minimize tokens.
        """
        try:
            products = compare_data.get("products", [])
            
            if not products:
                return json.dumps({
                    "type": "no-results",
                    "message": "Không có sản phẩm để so sánh"
                }, ensure_ascii=False)
            
            # Create minimal comparison
            minimal_products = []
            for product in products[:3]:  # Max 3 products for comparison
                minimal_product = self._create_minimal_product(product)
                minimal_products.append(minimal_product)
            
            response = {
                "type": "product-comparison",
                "message": f"So sánh {len(minimal_products)} sản phẩm",
                "products": minimal_products
            }
            
            json_response = json.dumps(response, ensure_ascii=False)
            logger.info(f"Compare response optimized: {estimate_tokens(json_response)} tokens")
            return json_response
            
        except Exception as e:
            logger.error(f"Error optimizing compare response: {e}")
            return json.dumps({
                "type": "error",
                "message": f"Lỗi khi so sánh: {str(e)}"
            }, ensure_ascii=False)
    
    def optimize_explore_response(self, explore_data: Dict[str, Any], user_query: str) -> str:
        """
        Optimize explore response để minimize tokens.
        """
        try:
            categories = explore_data.get("categories", [])
            
            if not categories:
                return json.dumps({
                    "type": "no-results",
                    "message": "Không tìm thấy danh mục nào"
                }, ensure_ascii=False)
            
            # Create minimal category list
            minimal_categories = []
            for category in categories[:5]:  # Max 5 categories
                minimal_categories.append({
                    "name": category.get("name", ""),
                    "count": category.get("count", 0)
                })
            
            response = {
                "type": "category-exploration",
                "message": f"Tìm thấy {len(minimal_categories)} danh mục",
                "categories": minimal_categories
            }
            
            json_response = json.dumps(response, ensure_ascii=False)
            logger.info(f"Explore response optimized: {estimate_tokens(json_response)} tokens")
            return json_response
            
        except Exception as e:
            logger.error(f"Error optimizing explore response: {e}")
            return json.dumps({
                "type": "error",
                "message": f"Lỗi khi khám phá: {str(e)}"
            }, ensure_ascii=False)

# Global instance
context_optimizer = ContextOptimizedToolWrapper(max_output_tokens=500)
