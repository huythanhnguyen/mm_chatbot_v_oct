"""
Dialog tools: save a concise dialog summary to artifacts for later retrieval.
"""

import json
import time
from typing import Any, Dict, Optional

from google.adk.tools import ToolContext

from .artifact_tools import write_json_artifact, artifact_reference
from .session_state import add_artifact_ref, get_conversation_context, set_last_user_question, update_preferences
from app.persistence_sqlite import save_dialog, save_artifact


async def save_dialog_summary(
    user_question: str,
    agent_answer: str,
    tool_context: ToolContext,
    intent: Optional[str] = None,
    key_info_json: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Persist a dialog summary artifact containing:
    - user_question
    - agent_answer (selected/concise)
    - intent (if provided or derived from conversation context)
    - key_info (optional JSON of important extracted facts)
    """
    try:
        # Update last user question into session context
        try:
            set_last_user_question(tool_context.state, user_question)
        except Exception:
            pass

        # Derive intent from conversation context if not provided
        if not intent:
            try:
                ctx = get_conversation_context(tool_context.state)
                intent = ctx.get("intent") or ctx.get("user_intent")
            except Exception:
                intent = None

        key_info: Optional[Dict[str, Any]] = None
        if isinstance(key_info_json, str) and key_info_json.strip():
            try:
                parsed = json.loads(key_info_json)
                if isinstance(parsed, dict):
                    key_info = parsed
            except Exception:
                key_info = None

        session_id = str(getattr(getattr(tool_context, 'session', None), 'id', 'unknown'))
        payload: Dict[str, Any] = {
            "type": "dialog_summary",
            "user_question": user_question or "",
            "agent_answer": agent_answer or "",
            "intent": intent or "",
            "key_info": key_info or {},
            "created_at": time.time(),
        }

        path = write_json_artifact(payload, category="dialog", session_id=session_id)
        add_artifact_ref(tool_context.state, "dialog", artifact_reference(path))
        try:
            save_artifact(session_id, "dialog", path)
            save_dialog(session_id, payload["user_question"], payload["agent_answer"], intent=payload["intent"], key_info=payload["key_info"])
        except Exception:
            pass

        return {
            "status": "success",
            "artifact_path": path,
            "message": "Dialog summary saved",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def set_user_preferences(preferences_json: str, tool_context: ToolContext) -> Dict[str, Any]:
    """Update user preferences in session state from a JSON string."""
    try:
        prefs: Dict[str, Any] = {}
        if isinstance(preferences_json, str) and preferences_json.strip():
            prefs = json.loads(preferences_json)
            if not isinstance(prefs, dict):
                prefs = {}
        update_preferences(tool_context.state, prefs)
        return {"status": "success", "preferences": prefs}
    except Exception as e:
        return {"status": "error", "message": str(e)}


