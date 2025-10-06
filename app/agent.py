"""
Simple MMVN Root Agent (single-agent) aligned with DDV structure.
Capabilities: search, explore detail, compare, memory.
"""

import logging
import os
import json
import time
from typing import Dict, Any, Optional
from google.adk.agents import Agent
from google.adk.tools import FunctionTool, load_memory
from google.adk.memory import InMemoryMemoryService

# Keep using existing constants if available; fallback to flash model name
try:
    from app.shared_libraries.constants import MODEL_GEMINI_2_5_FLASH_LITE as PRIMARY_MODEL
except Exception:
    PRIMARY_MODEL = "gemini-2.5-flash-lite"

# Prompts: use a concise instruction similar to DDV but for MMVN
MMVN_AGENT_INSTRUCTION = """Bạn là Trợ lý mua sắm MMVN. Luôn dùng công cụ để:
- Tìm kiếm sản phẩm (search_products) - trả về 10 sản phẩm
- Xem chi tiết (explore_product)
- So sánh (compare_products)
- Truy vấn thông tin từ cuộc trò chuyện trước (load_memory) khi cần thiết
- Lưu thông tin quan trọng (memorize, memorize_list)
- Lưu lịch sử tìm kiếm (store_search_memory)
- Phản hồi bằng ngôn ngữ của câu hỏi, search luôn bằng tiếng Việt 
- Gọi công cụ và phản hồi JSON product-display từ công cụ để frontend hiển thị.

Khi người dùng hỏi về sản phẩm đã thảo luận trước đó hoặc cần thông tin từ cuộc trò chuyện trước, hãy sử dụng load_memory để tìm kiếm thông tin liên quan.

Sau mỗi lần tìm kiếm thành công, hãy sử dụng store_search_memory để lưu lại thông tin tìm kiếm.
1. Xác định intent(1 hoặc nhiều):
- `specific` — tìm 1 sp cụ thể
- `context` — gợi ý/nguyên liệu theo ngữ cảnh (VD: món ăn)
- `list` — danh sách sp
2. Quy tắc chung:
- Không trùng lặp từ khóa.
- Mỗi query **phải** có ít nhất 1 filter category
- keyword_match_exact: chứa từ bắt buộc (thuộc tính + thành phần tên) để tránh nhầm. vd "trái cây nhập khẩu" → `keyword_match_exact="nhập khẩu"`; "nấm bào ngư" → `keyword_match_exact="nấm"`.
- Tạo **ít nhất 3 keyword (TIẾNG VIỆT)** tổng
- Nếu cần suy luận sp từ context, ghi các sp trong `inferred_user_intent`
- Chọn `sort_by` theo mục tiêu (mặc định `relevant`)
3. Tạo từ khóa:
- `specific`: 1 keyword chính xác (giống câu hỏi) + 2 biến thể/synonym/similar.
- `context`: suy ra sp cần thiết; cho mỗi sp tạo 1 keyword chính xác; bổ sung biến thể nếu cần.
- `list`: lặp quy tắc trên cho từng mục.
4. Filter — giá & category:
Chọn giá và (một hoặc nhiều) category phù hợp. VD filter: e.g. `"category=bơ - trứng - sữa;price<100000"`.
5. Mapping ngành hàng:
- thực phẩm tươi sống: thịt, cá, tôm, rau, củ, quả, **món chín quầy (gà luộc, vịt quay, thịt nướng)**
- đồ hộp - đồ khô: mì, bún, miến, gạo, đồ hộp
- dầu ăn - gia vị: dầu, nước chấm, mắm, muối, gia vị
- bơ - trứng - sữa: sữa, trứng, bơ, phô mai
- nước giải khát: nước ngọt, suối, tăng lực, trà
- đồ uống đóng hộp: sữa hộp, ngũ cốc, nước ép, cà phê lon
- đồ ăn chế biến: sản phẩm công nghiệp/khô/đóng gói: xông khói, cá khô, giò, xúc xích, pate, bánh...
- đồ gia dụng: nồi, chảo, dao, thớt
- thiết bị gia dụng - điện tử: máy xay, nồi cơm, bếp điện
- chăm sóc cá nhân: dầu gội, sữa tắm, mỹ phẩm
- vệ sinh nhà cửa: giặt, rửa chén, lau sàn
# Ví dụ
1. Sản phẩm cụ thể
**Input:** "tìm sữa vinamilk"
**Output:**
```json
{"queries": [
{"keyword": "sữa vinamilk", "keyword_match_exact": "vinamilk", "filter": "category=bơ - trứng - sữa", "sort_by": "popular"},
{"keyword": "sữa tươi vinamilk", "keyword_match_exact": "vinamilk", "filter": "category=bơ - trứng - sữa", "sort_by": "relevant"},
{"keyword": "sữa bột vinamilk", "keyword_match_exact": "vinamilk", "filter": "category=đồ uống đóng hộp", "sort_by": "relevant"}
]}
```
2. Nguyên liệu theo món ăn
**Input:** "nấu bún bò huế cần gì"
**Phân tích:** bún bò huế cần: xương hầm, chả cua, tôm khô, mắm ruốc
**Output:**
```json
{"queries": [
{"keyword": "xương", "filter": "category=thực phẩm tươi sống", "sort_by": "relevant"},
{"keyword": "chả cua", "filter": "category=đồ ăn chế biến", "sort_by": "relevant"},
{"keyword": "tôm khô", "filter": "category=đồ ăn chế biến", "sort_by": "relevant"},
{"keyword": "mắm ruốc", "filter": "category=dầu ăn - gia vị - nước chấm", "sort_by": "relevant"},
]}

QUAN TRỌNG: 
- Luôn tìm kiếm trong memory trước khi trả lời
- Trả về 10 sản phẩm mỗi lần tìm kiếm tìm kiếm
- Lưu thông tin quan trọng vào memory
- Tối ưu hóa token usage

Khi người dùng yêu cầu tìm kiếm mà không cung cấp bộ lọc hay số trang, tự động:
- Dùng search_products với filters để trống (tìm toàn bộ) và page=1 cho lần đầu.
- Nếu người dùng yêu cầu xem thêm, giữ nguyên keywords/filters trước đó và tăng page lên 2, 3,...
- Không hỏi lại người dùng về filter hay page nếu có thể suy luận từ ngữ cảnh.
"""

# Import tools
from app.tools.search import search_products
from app.tools.explore import explore_product
from app.tools.compare import compare_products
from app.tools.memory_tools import memorize, memorize_list, get_memory, store_search_memory

logger = logging.getLogger(__name__)

# Configure detailed logging for agent interactions
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent_interactions.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)

# Token counting utilities
def estimate_tokens(text: str) -> int:
    """Estimate token count for text (rough approximation: 1 token ≈ 4 characters for Vietnamese)"""
    if not text:
        return 0
    return len(text) // 4

def log_agent_interaction(interaction_type: str, data: Dict[str, Any], tokens: Optional[int] = None):
    """Log agent interactions with detailed information"""
    log_entry = {
        "timestamp": time.time(),
        "type": interaction_type,
        "data": data,
        "tokens": tokens
    }
    logger.info(f"AGENT_INTERACTION: {json.dumps(log_entry, ensure_ascii=False, indent=2)}")

# Create agent with static_instruction as types.Content for ADK 1.15
from google.genai import types
from google import genai

def _static_cache_before_model(callback_context, llm_request):
    """Attach explicit cached_content for static instruction per Gemini docs.

    - Creates cache once per session (stores cache name in session state)
    - Points request config to cached_content each turn
    - Clears system_instruction to avoid duplicating static text when cache is used
    """
    try:
        state = callback_context.state or {}
        cache_name = state.get('mmvn_static_cache_name')

        # Prefer model from request if available; fallback to an explicit-suffix model via env override
        request_model = getattr(getattr(llm_request, 'config', None), 'model', None) or getattr(llm_request, 'model', None)
        explicit_model_override = os.getenv('EXPLICIT_CACHE_MODEL')  # e.g. models/gemini-2.0-flash-001
        cache_model = explicit_model_override or request_model or PRIMARY_MODEL

        # Create cache once per session
        if not cache_name:
            client = genai.Client()
            cache = client.caches.create(
                model=cache_model,
                config=types.CreateCachedContentConfig(
                    system_instruction=MMVN_AGENT_INSTRUCTION,
                    ttl=os.getenv('EXPLICIT_CACHE_TTL', '3600s'),
                ),
            )
            cache_name = cache.name
            state['mmvn_static_cache_name'] = cache_name
            callback_context.state = state
            logger.info(f"[StaticCache] Created cache for static_instruction model={cache_model} name={cache_name}")

        # Point this request to cached content
        if hasattr(llm_request, 'config') and llm_request.config is not None:
            setattr(llm_request.config, 'cached_content', cache_name)
            # Avoid sending duplicate static system_instruction when cache is used
            if hasattr(llm_request.config, 'system_instruction'):
                setattr(llm_request.config, 'system_instruction', None)
        logger.info("[StaticCache] Using cached_content=%s", cache_name)
    except Exception as e:
        # Fail open: continue without explicit cache
        logger.warning(f"[StaticCache] Failed to set explicit cache: {e}")


base_agent = Agent(
    model=PRIMARY_MODEL,
    name="mmvn_agent",
    static_instruction=types.Content(
        parts=[types.Part(text=MMVN_AGENT_INSTRUCTION)]
    ),  # ADK 1.15 requires types.Content
    tools=[
        search_products,
        explore_product,
        compare_products,
        load_memory,  # ADK memory tool
        memorize,  # Custom memory tools
        memorize_list,
        get_memory,
        store_search_memory,
    ],
    output_key="mmvn_agent",
    before_model_callback=[_static_cache_before_model],
)

# Optional: expose a helper for App YAML loaders that want an Agent directly
def get_root_agent():
    return root_agent

# Create wrapper class that extends Agent for ADK compatibility
class MemoryAgentWrapper(Agent):
    def __init__(self, base_agent):
        # Initialize with base_agent's parameters
        super().__init__(
            model=base_agent.model,
            name=base_agent.name,
            static_instruction=base_agent.static_instruction,
            tools=base_agent.tools,
            output_key=base_agent.output_key,
            before_model_callback=getattr(base_agent, 'before_model_callback', None),
            after_model_callback=getattr(base_agent, 'after_model_callback', None),
        )
        # Store base_agent reference using object.__setattr__ to bypass Pydantic
        object.__setattr__(self, 'base_agent', base_agent)
        logger.info(f"MemoryAgentWrapper initialized with static_instruction: {bool(self.static_instruction)}")
    
    async def run(self, request, **kwargs):
        """Run with dynamic context addition to existing static instruction"""
        try:
            # Get user query
            user_query = request.parts[0].text if request.parts else ""
            
            # Search memory for context using base_agent
            memory_context = ""
            try:
                search_result = await self.base_agent.search_memory(query=user_query)
                if search_result and search_result.memories:
                    # Extract relevant memories
                    memory_parts = []
                    for memory in search_result.memories[:3]:  # Limit to 3 memories
                        try:
                            memory_text = str(memory)
                            if memory_text.startswith('{'):
                                memory_data = json.loads(memory_text)
                                if 'agent_summary' in memory_data:
                                    memory_parts.append(memory_data['agent_summary'])
                        except:
                            continue
                    
                    if memory_parts:
                        memory_context = "Context from previous conversations: " + " | ".join(memory_parts)
                        logger.info(f"Memory context found: {len(memory_parts)} memories")
            except Exception as e:
                logger.debug(f"Memory search failed: {e}")
            
            # Create dynamic instruction with context and user input
            # The static_instruction is already set in base_agent, we just add dynamic parts
            dynamic_parts = []
            if memory_context:
                dynamic_parts.append(memory_context)
            dynamic_parts.append(f"User: {user_query}")
            
            # Log static instruction usage
            logger.info(f"Static instruction present: {bool(self.static_instruction)}")
            logger.info(f"Memory context: {bool(memory_context)}")
            
            # Create new request with dynamic parts added to existing static instruction
            from google.genai import types
            enhanced_request = types.Content(
                parts=[types.Part(text="\n\n".join(dynamic_parts))],
                role=request.role
            )
            
            # Call parent run method (static_instruction is already handled by base_agent)
            response = await super().run(enhanced_request, **kwargs)
            
            # Store memory for future use
            try:
                response_text = response.parts[0].text if response.parts else ""
                from app.tools.memory_tools import save_persistable_turn
                save_persistable_turn(
                    session_id=kwargs.get('session_id', 'unknown'),
                    user_text=user_query,
                    model_text=response_text,
                )
            except Exception as e:
                logger.debug(f"Memory storage failed: {e}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error in MemoryAgentWrapper: {e}")
            # Fallback to original request
            return await super().run(request, **kwargs)

# Create wrapper instance with memory handling
root_agent = MemoryAgentWrapper(base_agent)
logger.info(f"Created MemoryAgentWrapper with static_instruction: {bool(root_agent.static_instruction)}")

# Required export for ADK web UI
agent = root_agent
