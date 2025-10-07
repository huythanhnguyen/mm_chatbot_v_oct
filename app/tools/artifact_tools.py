import os
import json
import time
import base64
from typing import Any, Dict, Optional

# Simple JSON artifact writer (filesystem-based) for portability
# In production you could replace with cloud storage or ADK artifact store


def _sanitize_filename(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in name)
    return safe[:120] or "artifact"


def write_json_artifact(payload: Dict[str, Any], *, category: str, session_id: Optional[str] = None, base_dir: str = "artifacts") -> str:
    os.makedirs(base_dir, exist_ok=True)
    ts = int(time.time())
    sid = _sanitize_filename(session_id or "session")
    cat = _sanitize_filename(category)
    filename = f"{cat}__{sid}__{ts}.json"
    path = os.path.join(base_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def artifact_reference(path: str, *, mime_type: str = "application/json") -> Dict[str, Any]:
    """Return a lightweight reference that can be stored in memory/state."""
    return {
        "type": "artifact",
        "mime_type": mime_type,
        "path": path,
        "created_at": time.time(),
    }


