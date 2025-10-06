# Agent Logging và Analytics Guide

## Tổng quan

Hệ thống logging đã được tích hợp vào MMVN Agent để theo dõi và phân tích:
- Tất cả input và prompt của agent
- Output và response của agent  
- Token usage và cost estimation
- Performance metrics
- Tool usage statistics

## Các thành phần chính

### 1. Agent Logging (`app/agent.py`, `app/memory_agent.py`)

**Tính năng:**
- Log tất cả input từ user
- Log enhanced prompts (với memory context)
- Log LLM responses
- Log memory search results
- Tính toán tokens cho input/output
- Theo dõi performance metrics

**Log types:**
- `INPUT_RECEIVED`: Input gốc từ user
- `MEMORY_SEARCH`: Kết quả tìm kiếm memory
- `PROMPT_ENHANCED`: Prompt đã được enhance với memory context
- `LLM_RESPONSE`: Response từ LLM
- `SESSION_SUMMARY`: Tổng kết session
- `AGENT_ERROR`: Lỗi trong quá trình xử lý

### 2. Tool Logging (`app/tools/`)

**Tính năng:**
- Log tool usage và input parameters
- Log tool completion và output
- Log tool errors
- Theo dõi processing time

**Log types:**
- `TOOL_USAGE`: Tool được gọi với parameters
- `TOOL_COMPLETION`: Tool hoàn thành thành công
- `TOOL_ERROR`: Tool gặp lỗi

### 3. Analytics System (`app/agent_analytics.py`)

**Tính năng:**
- Parse logs và tạo thống kê
- Phân tích token usage patterns
- Performance metrics analysis
- Session analysis
- Cost estimation

## Cách sử dụng

### 1. Chạy Agent với Logging

Logging sẽ tự động hoạt động khi agent chạy. Logs được lưu vào file `agent_interactions.log`.

```python
from app.agent import agent
from google.genai import types

# Agent sẽ tự động log tất cả interactions
request = types.Content(parts=[types.Part(text="Tìm kiếm điện thoại iPhone")])
response = await agent.run(request, session_id="user_123")
```

### 2. Xem Analytics

```bash
# Chạy analytics dashboard
python run_analytics.py

# Hoặc import trực tiếp
from app.agent_analytics import AgentAnalytics
analytics = AgentAnalytics()
analytics.print_analytics_report(hours_back=24)
```

### 3. Test Logging System

```bash
# Chạy test để kiểm tra logging
python test_agent_logging.py
```

## Log Format

### Agent Interaction Logs

```json
{
  "timestamp": 1703123456.789,
  "type": "INPUT_RECEIVED",
  "data": {
    "session_id": "user_123",
    "user_query": "Tìm kiếm điện thoại iPhone",
    "request_role": "user",
    "request_parts_count": 1
  },
  "tokens": 8
}
```

### Tool Usage Logs

```json
{
  "timestamp": 1703123456.789,
  "tool": "search_products",
  "input": {
    "keywords": "điện thoại iPhone",
    "filters": null
  }
}
```

## Analytics Metrics

### 1. Summary Statistics
- Total sessions
- Total interactions
- Average interactions per session
- Interaction type distribution

### 2. Token Analysis
- Total tokens used
- Average tokens per interaction
- Token usage by interaction type
- Min/max/median token usage

### 3. Performance Metrics
- Total processing time
- LLM processing time
- Memory search time
- Average response times

### 4. Session Analysis
- Session length distribution
- Session duration
- User engagement patterns

## Cost Estimation

Hệ thống cung cấp cost estimation dựa trên token usage:

```python
from app.agent_analytics import estimate_cost

# Estimate cost for 10,000 tokens
cost = estimate_cost(10000, model="gemini-2.5-flash-lite")
print(f"Total cost: ${cost['total_cost_usd']:.4f}")
```

**Pricing (approximate):**
- Input tokens: $0.075 per 1K tokens
- Output tokens: $0.30 per 1K tokens

## Token Estimation

Token estimation sử dụng approximation: **1 token ≈ 4 characters** cho tiếng Việt.

```python
from app.agent import estimate_tokens

tokens = estimate_tokens("Xin chào, tôi muốn tìm kiếm sản phẩm")
print(f"Estimated tokens: {tokens}")
```

## Monitoring và Alerts

### 1. High Token Usage Alert
```python
# Check for high token usage
if total_tokens > 50000:  # 50K tokens threshold
    logger.warning(f"High token usage detected: {total_tokens} tokens")
```

### 2. Performance Monitoring
```python
# Check for slow responses
if processing_time > 10.0:  # 10 seconds threshold
    logger.warning(f"Slow response detected: {processing_time}s")
```

## Best Practices

### 1. Log Management
- Rotate log files regularly
- Monitor log file size
- Archive old logs

### 2. Performance Monitoring
- Set up alerts for high token usage
- Monitor response times
- Track error rates

### 3. Cost Management
- Set daily/monthly token limits
- Monitor cost trends
- Optimize prompts to reduce token usage

## Troubleshooting

### 1. Log File Not Found
```bash
# Check if log file exists
ls -la agent_interactions.log

# If not found, check logging configuration
```

### 2. High Memory Usage
```python
# Check for memory leaks in logging
# Consider log rotation for large files
```

### 3. Performance Issues
```python
# Disable detailed logging in production if needed
# Use log levels to control verbosity
```

## File Structure

```
app/
├── agent.py                 # Main agent with logging
├── memory_agent.py          # Memory agent with enhanced logging
├── agent_analytics.py       # Analytics and reporting
├── tools/
│   ├── search.py           # Search tool with logging
│   ├── explore.py          # Explore tool with logging
│   └── compare.py          # Compare tool with logging
├── agent_interactions.log  # Main log file
├── run_analytics.py        # Analytics runner
└── test_agent_logging.py   # Test script
```

## Kết luận

Hệ thống logging và analytics này cung cấp:
- ✅ Complete visibility vào agent operations
- ✅ Token usage tracking và cost estimation
- ✅ Performance monitoring
- ✅ Detailed analytics và reporting
- ✅ Easy integration với existing codebase

Sử dụng hệ thống này để optimize agent performance, monitor costs, và improve user experience.

