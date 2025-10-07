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

# Optimized instruction for faster responses
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
from app.tools.dialog_tools import save_dialog_summary, set_user_preferences

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


# Direct agent creation without wrapper overhead
root_agent = Agent(
    model=PRIMARY_MODEL,
    name="mmvn_agent",
    static_instruction=types.Content(
        parts=[types.Part(text=MMVN_AGENT_INSTRUCTION)]
    ),
    tools=[
        search_products,
        explore_product,
        compare_products,
        load_memory,
        memorize,
        memorize_list,
        get_memory,
        store_search_memory,
        save_dialog_summary,
        set_user_preferences,
    ],
    output_key="mmvn_agent",
)

# Required export for ADK web UI
agent = root_agent
