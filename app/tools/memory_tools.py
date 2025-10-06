"""
Memory Tools - Áp dụng patterns từ Travel Concierge
Dựa trên: travel_concierge/tools/memory.py

Mở rộng theo chính sách ADK-aligned trong memory-tasklog.md:
- Chỉ lưu user input/summary và LLM output
- Không lưu ToolRequest/ToolResult
- Redact PII trước khi persist
"""

import json
import re
import time
import logging
from typing import Dict, Any, Optional, List
from google.adk.tools import ToolContext
from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)

# --- Redaction utilities (PII masking) ---
PII_PATTERNS = [
    re.compile(r"[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\+?\d[\d .-]{7,}\b"),
]

def redact(text: Optional[str]) -> Optional[str]:
    """Mask common PII before persisting."""
    if not text:
        return text
    redacted = text
    for pat in PII_PATTERNS:
        redacted = pat.sub("[REDACTED]", redacted)
    return redacted

# --- Event filtering helpers ---
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
    """Persist filtered session events if a memory service is available on session.

    This function is defensive to fit different session shapes.
    """
    try:
        events: List[Dict[str, Any]] = []
        for e in getattr(session, 'events', []) or []:
            if isinstance(e, dict) and is_persistable_event(e):
                events.append(e)

        record = {
            'sessionId': getattr(session, 'id', None),
            'user_messages': [redact(e.get('text', '')) for e in events if e.get('kind') == 'UserMessage' and e.get('text')],
            'user_media_summaries': [
                {
                    'summary': redact(e.get('summary', '')),
                    'modality': e.get('modality'),
                    'meta': {k: (e.get('meta') or {}).get(k) for k in ['language', 'mime', 'durationMs', 'sha256']},
                }
                for e in events if e.get('kind') == 'UserMessage' and e.get('summary')
            ],
            'model_responses': [redact(e.get('text', '')) for e in events if e.get('kind') == 'ModelResponse'],
            'meta': {
                'startedAt': getattr(session, 'startedAt', None),
                'endedAt': getattr(session, 'endedAt', None),
                'locale': getattr(getattr(session, 'state', None), 'get', lambda *_: None)('user.locale') if getattr(session, 'state', None) else None,
                'intent': getattr(getattr(session, 'state', None), 'get', lambda *_: None)('conversation.intentSummary') if getattr(session, 'state', None) else None,
            },
        }

        # Prefer a memory service if present
        mem_svc = getattr(session, 'memory', None)
        if mem_svc and hasattr(mem_svc, 'upsert'):
            mem_svc.upsert(record)
            return

        # Fallback: append to a local JSONL file for auditing
        with open('memory_persisted.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"persist_memory_from_session failed: {e}")

def put_tool_cache(state: Any, key: str, value: Any, ttl_seconds: int = 900) -> None:
    """Put tool results into ephemeral state (non-persistent)."""
    try:
        namespaced = f"tool.temp.{key}"
        if hasattr(state, 'set'):
            state.set(namespaced, value, ttl=ttl_seconds, persist=False, ephemeral=True)
        else:
            # Fallback: simple attribute/dict set without persistence
            if isinstance(state, dict):
                state[namespaced] = value
    except Exception as e:
        logger.debug(f"put_tool_cache failed: {e}")

_INMEM_TURNS: Dict[str, list] = {}

def save_persistable_turn(session_id: str, user_text: Optional[str], model_text: Optional[str], media_summary: Optional[Dict[str, Any]] = None) -> None:
    """Store only in-memory: user text/media summary and LLM text per turn."""
    try:
        record = {
            'user_text': redact(user_text) if user_text else None,
            'user_media_summary': media_summary or None,
            'model_text': redact(model_text) if model_text else None,
            'ts': time.time(),
        }
        bucket = _INMEM_TURNS.setdefault(session_id or 'unknown', [])
        bucket.append(record)
    except Exception as e:
        logger.debug(f"save_persistable_turn failed: {e}")

def memorize(key: str, value: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Memorize pieces of information, one key-value pair at a time.
    Áp dụng pattern từ Travel Concierge.
    
    Args:
        key: the label indexing the memory to store the value.
        value: the information to be stored.
        tool_context: The ADK tool context.
    
    Returns:
        A status message.
    """
    try:
        mem_dict = tool_context.state
        mem_dict[key] = value
        
        logger.info(f"Memory stored: {key} = {value[:100]}...")
        
        return {"status": f'Stored "{key}": "{value[:50]}..."'}
    except Exception as e:
        logger.error(f"Error storing memory: {e}")
        return {"status": f"Error storing memory: {str(e)}"}

def memorize_list(key: str, value: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Memorize pieces of information as a list.
    
    Args:
        key: the label indexing the memory to store the value.
        value: the information to be stored.
        tool_context: The ADK tool context.
    
    Returns:
        A status message.
    """
    try:
        mem_dict = tool_context.state
        if key not in mem_dict:
            mem_dict[key] = []
        if value not in mem_dict[key]:
            mem_dict[key].append(value)
        
        logger.info(f"Memory list updated: {key} += {value[:50]}...")
        
        return {"status": f'Added to "{key}": "{value[:50]}..."'}
    except Exception as e:
        logger.error(f"Error storing memory list: {e}")
        return {"status": f"Error storing memory list: {str(e)}"}

def forget(key: str, value: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Forget pieces of information.
    
    Args:
        key: the label indexing the memory to store the value.
        value: the information to be removed.
        tool_context: The ADK tool context.
    
    Returns:
        A status message.
    """
    try:
        if key not in tool_context.state:
            return {"status": f'Key "{key}" not found'}
        
        if isinstance(tool_context.state[key], list):
            if value in tool_context.state[key]:
                tool_context.state[key].remove(value)
                return {"status": f'Removed from "{key}": "{value}"'}
            else:
                return {"status": f'Value not found in "{key}"'}
        else:
            if tool_context.state[key] == value:
                del tool_context.state[key]
                return {"status": f'Removed "{key}": "{value}"'}
            else:
                return {"status": f'Value does not match for "{key}"'}
    except Exception as e:
        logger.error(f"Error removing memory: {e}")
        return {"status": f"Error removing memory: {str(e)}"}

def get_memory(key: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Get stored memory by key.
    
    Args:
        key: the label indexing the memory to retrieve.
        tool_context: The ADK tool context.
    
    Returns:
        The stored value or error message.
    """
    try:
        if key not in tool_context.state:
            return {"status": f'Key "{key}" not found', "value": None}
        
        value = tool_context.state[key]
        logger.info(f"Memory retrieved: {key} = {str(value)[:100]}...")
        
        return {"status": "success", "value": value}
    except Exception as e:
        logger.error(f"Error retrieving memory: {e}")
        return {"status": f"Error retrieving memory: {str(e)}", "value": None}

def list_memories(tool_context: ToolContext) -> Dict[str, Any]:
    """
    List all stored memories.
    
    Args:
        tool_context: The ADK tool context.
    
    Returns:
        Dictionary of all stored memories.
    """
    try:
        memories = dict(tool_context.state)
        logger.info(f"Listed {len(memories)} memories")
        
        return {"status": "success", "memories": memories}
    except Exception as e:
        logger.error(f"Error listing memories: {e}")
        return {"status": f"Error listing memories: {str(e)}", "memories": {}}

def clear_memories(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Clear all memories.
    
    Args:
        tool_context: The ADK tool context.
    
    Returns:
        Status message.
    """
    try:
        tool_context.state.clear()
        logger.info("All memories cleared")
        
        return {"status": "All memories cleared"}
    except Exception as e:
        logger.error(f"Error clearing memories: {e}")
        return {"status": f"Error clearing memories: {str(e)}"}

def store_search_memory(query: str, results_count: int, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Store search-specific memory.
    
    Args:
        query: The search query.
        results_count: Number of results found.
        tool_context: The ADK tool context.
    
    Returns:
        Status message.
    """
    try:
        search_memory = {
            "query": query,
            "results_count": results_count,
            "timestamp": time.time(),
            "type": "search"
        }
        
        # Store in search history
        memorize_list("search_history", json.dumps(search_memory, ensure_ascii=False), tool_context)
        
        # Store latest search
        memorize("latest_search", json.dumps(search_memory, ensure_ascii=False), tool_context)
        
        logger.info(f"Search memory stored: {query} -> {results_count} results")
        
        return {"status": f"Search memory stored: {query} -> {results_count} results"}
    except Exception as e:
        logger.error(f"Error storing search memory: {e}")
        return {"status": f"Error storing search memory: {str(e)}"}

def store_user_preference(key: str, value: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Store user preference.
    
    Args:
        key: Preference key (e.g., "price_range", "category_preference").
        value: Preference value.
        tool_context: The ADK tool context.
    
    Returns:
        Status message.
    """
    try:
        preference_key = f"user_preference_{key}"
        memorize(preference_key, value, tool_context)
        
        # Also store in preferences list
        memorize_list("user_preferences", f"{key}:{value}", tool_context)
        
        logger.info(f"User preference stored: {key} = {value}")
        
        return {"status": f"User preference stored: {key} = {value}"}
    except Exception as e:
        logger.error(f"Error storing user preference: {e}")
        return {"status": f"Error storing user preference: {str(e)}"}

def get_user_preferences(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Get all user preferences.
    
    Args:
        tool_context: The ADK tool context.
    
    Returns:
        Dictionary of user preferences.
    """
    try:
        preferences = {}
        memories = dict(tool_context.state)
        
        for key, value in memories.items():
            if key.startswith("user_preference_"):
                pref_key = key.replace("user_preference_", "")
                preferences[pref_key] = value
        
        logger.info(f"Retrieved {len(preferences)} user preferences")
        
        return {"status": "success", "preferences": preferences}
    except Exception as e:
        logger.error(f"Error retrieving user preferences: {e}")
        return {"status": f"Error retrieving user preferences: {str(e)}", "preferences": {}}

# Export all functions
__all__ = [
    'memorize', 'memorize_list', 'forget', 'get_memory', 'list_memories',
    'clear_memories', 'store_search_memory', 'store_user_preference', 'get_user_preferences',
    'redact', 'is_persistable_event', 'persist_memory_from_session', 'put_tool_cache', 'save_persistable_turn'
]
