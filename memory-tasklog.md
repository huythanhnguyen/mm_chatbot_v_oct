## Chính sách bộ nhớ (ADK-aligned) cho MM Search Bot

Mục tiêu: Chỉ lưu các thông tin do người dùng cung cấp (hoặc summary khi input là voice/image) và phản hồi từ LLM; không lưu dữ liệu trả về từ tool hay dấu vết thực thi nội bộ.

### 1) Phạm vi lưu trữ
- Lưu:
  - User input dạng text (đã qua redaction).
  - User input dạng voice/image: chỉ lưu summary text + metadata cần thiết (modality, lang, mime, durationMs, sha256), không lưu payload gốc.
  - LLM output (text) sau redaction; không lưu function_call args hay tool traces.
- Không lưu:
  - ToolRequest/ToolResult (mọi công cụ, bao gồm tham số truy vấn, payload trả về).
  - System/Debug logs, internal planner traces, chain-of-thought, IDs nội bộ.

### 2) Luồng ADK: Session / State / Memory
- Session (events): Gắn hook lọc trước khi ghi/persist lịch sử phiên.
- State (tạm thời): Lưu cache tool, retrieval, features… với TTL và persist=false.
- Memory (dài hạn): Chỉ ghi từ “session summary” đã lọc, dạng nén.

### 3) Hook lọc sự kiện Session
Logic lọc sự kiện trước khi persist lịch sử phiên (ngôn ngữ-agnostic):

```ts
function isPersistableEvent(e) {
  if (e.kind === 'UserMessage' && e.modality === 'text') return true;
  if (e.kind === 'UserMessage' && (e.modality === 'voice' || e.modality === 'image')) {
    return Boolean(e.summary); // yêu cầu đã có summary
  }
  if (e.kind === 'ModelResponse' && e.channel === 'text') return true;
  return false; // loại ToolRequest/ToolResult và các loại khác
}

session.on('beforePersist', (events) => {
  return events
    .map((e) => {
      if (e.kind === 'UserMessage' && (e.modality === 'voice' || e.modality === 'image')) {
        return {
          kind: 'UserMessage',
          modality: e.modality,
          summary: redact(e.summary),
          meta: pick(e.meta, ['language', 'mime', 'durationMs', 'sha256']),
          ts: e.ts,
        };
      }
      if (e.kind === 'ModelResponse') {
        return { kind: 'ModelResponse', text: redact(e.text), ts: e.ts };
      }
      if (e.kind === 'UserMessage' && e.modality === 'text') {
        return { kind: 'UserMessage', text: redact(e.text), ts: e.ts };
      }
      return null;
    })
    .filter(Boolean);
});
```

### 4) Quy ước State (không persist)
- Namespaces: `tool.temp.*`, `retrieval.cache.*`, `features.*`.
- TTL ngắn (10–30 phút), `persist: false`, `ephemeral: true`.

```ts
state.set('tool.temp.searchResults', results, { ttlMs: 15 * 60_000, persist: false, ephemeral: true });
state.set('retrieval.cache.vectorIds', ids, { ttlMs: 10 * 60_000, persist: false });
```

### 5) Ghi Memory dài hạn theo checkpoint
- Nguồn: tập sự kiện đã lọc hoặc session summary cuối phiên/cuối lượt.
- Cấu trúc mẫu:

```ts
function persistMemoryFromSession(session) {
  const evts = session.events.filter(isPersistableEvent);
  const record = {
    sessionId: session.id,
    user_messages: evts.filter(e => e.kind==='UserMessage' && e.text).map(e => e.text),
    user_media_summaries: evts.filter(e => e.kind==='UserMessage' && e.summary).map(e => ({
      summary: e.summary,
      modality: e.modality,
      meta: e.meta,
    })),
    model_responses: evts.filter(e => e.kind==='ModelResponse').map(e => e.text),
    meta: {
      startedAt: session.startedAt,
      endedAt: Date.now(),
      locale: session.state.get('user.locale'),
      intent: session.state.get('conversation.intentSummary'),
    },
  };
  memory.upsert(record);
}
```

### 6) Tóm tắt media (voice/image)
- Voice: ASR → text → tóm tắt 1–3 câu; lưu summary + `durationMs`, `lang`, `sha256` file, không lưu transcript gốc nếu không cần.
- Image: Vision captioning → caption/tags; lưu caption summary + loại ảnh + mime; không lưu pixel.

### 7) Redaction/Anonymization
- Áp dụng trước khi persist: che PII/secret (email, phone, thẻ, token, địa chỉ chi tiết…)
- Loại bỏ function_call args, tool params, internal IDs, raw URLs nhạy cảm.

### 8) Retention
- Session (đã lọc): 30–90 ngày tùy yêu cầu.
- Memory: lâu dài nhưng chỉ giữ summary/intent, không raw tool data.
- State/cache tool: TTL ngắn, không persist.

---

## Tích hợp vào repo này (Python)

Các điểm chèn/hook khuyến nghị:

1) `app/tools/memory_tools.py`
- Thêm hàm `redact(text: str) -> str` để che PII.
- Thêm adapter `persist_memory_from_session(session)` theo cấu trúc ở trên.
- Thêm helper `is_persistable_event(e)` (phiên bản Python) để lọc event.

2) `app/agent.py`
- Tại điểm kết thúc mỗi lượt (sau khi nhận phản hồi LLM), gọi `persist_memory_from_session(session)`.
- Khi ghi lịch sử phiên: áp dụng pipeline lọc sự kiện trước khi log/persist.
- Đảm bảo phản hồi tool và traces chỉ đi vào `session.state` hoặc log debug (không persist dài hạn).

3) `app/memory_config.py`
- Thêm cấu hình retention (days) cho session log đã lọc và memory.
- Thêm flags cho namespaces không persist: `tool.temp.*`, `retrieval.cache.*`.

4) `app/tools/context_optimized_tools.py` và `app/tools/*`
- Mọi kết quả tool: đặt vào `session.state` với TTL và `persist=False`.
- Nếu cần dùng lại nhiều lượt, cache bằng key `retrieval.cache.*` vẫn `persist=False`.

5) `app/log_api.py`
- Khi gửi log ra ngoài: chỉ gửi sự kiện đã lọc (user input, media summary, LLM text). Ẩn tool payload.

6) Frontend (`frontend/src/services/*`)
- Nếu truyền media: gửi checksum/hash và metadata cần thiết; tránh tải/persist file raw ở backend nếu không bắt buộc.

---

## Gợi ý triển khai nhanh (Python snippets)

```python
# app/tools/memory_tools.py
import re
from typing import Any, Dict, List

PII_PATTERNS = [
    re.compile(r"[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\+?\d[\d .-]{7,}\b"),
]

def redact(text: str) -> str:
    if not text:
        return text
    redacted = text
    for pat in PII_PATTERNS:
        redacted = pat.sub("[REDACTED]", redacted)
    return redacted


def is_persistable_event(e: Dict[str, Any]) -> bool:
    kind = e.get('kind')
    modality = e.get('modality')
    channel = e.get('channel')
    if kind == 'UserMessage' and modality == 'text':
        return True
    if kind == 'UserMessage' and modality in ('voice', 'image'):
        return bool(e.get('summary'))
    if kind == 'ModelResponse' and channel == 'text':
        return True
    return False


def persist_memory_from_session(session) -> None:
    events: List[Dict[str, Any]] = [e for e in session.events if is_persistable_event(e)]
    record = {
        'sessionId': session.id,
        'user_messages': [redact(e.get('text', '')) for e in events if e.get('kind') == 'UserMessage' and e.get('text')],
        'user_media_summaries': [
            {
                'summary': redact(e.get('summary', '')),
                'modality': e.get('modality'),
                'meta': {k: e.get('meta', {}).get(k) for k in ['language', 'mime', 'durationMs', 'sha256']},
            }
            for e in events if e.get('kind') == 'UserMessage' and e.get('summary')
        ],
        'model_responses': [redact(e.get('text', '')) for e in events if e.get('kind') == 'ModelResponse'],
        'meta': {
            'startedAt': getattr(session, 'startedAt', None),
            'endedAt': getattr(session, 'endedAt', None),
            'locale': session.state.get('user.locale') if hasattr(session, 'state') else None,
            'intent': session.state.get('conversation.intentSummary') if hasattr(session, 'state') else None,
        },
    }
    # TODO: implement actual storage (DB/file/cloud). Placeholder:
    if hasattr(session, 'memory'):  # e.g., injected memory service
        session.memory.upsert(record)


def put_tool_cache(state, key: str, value: Any, ttl_seconds: int = 900) -> None:
    # Persist=false, ephemeral cache
    namespaced = f"tool.temp.{key}"
    state.set(namespaced, value, ttl=ttl_seconds, persist=False, ephemeral=True)
```

```python
# app/agent.py (điểm gọi sau khi có phản hồi LLM)
from app.tools.memory_tools import persist_memory_from_session

# ... trong hàm xử lý mỗi lượt hội thoại
persist_memory_from_session(session)
```

---

## Kiểm thử
- Kiểm tra rằng ToolRequest/ToolResult không xuất hiện trong bản ghi memory/log dài hạn.
- Kiểm tra media: chỉ có summary + metadata, không có blob/raw.
- Kiểm tra redaction: email/số điện thoại bị che.
- Kiểm tra TTL: state key `tool.temp.*` tự hết hạn, không persist.

