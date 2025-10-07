import time
from typing import Any, Dict, List, Optional


SESSION_ROOT_KEY = "mmvn_session"


def _ensure_session_dict(state: Dict[str, Any]) -> Dict[str, Any]:
    if SESSION_ROOT_KEY not in state or not isinstance(state[SESSION_ROOT_KEY], dict):
        state[SESSION_ROOT_KEY] = {}
    session = state[SESSION_ROOT_KEY]
    # Initialize standard sections if missing
    session.setdefault("current_search", {})
    session.setdefault("pagination", {"page": 1, "page_size": 10})
    session.setdefault("preferences", {})
    session.setdefault("context", {})
    session.setdefault("temp_cart", {"items": []})
    session.setdefault("timestamps", {})
    session.setdefault("artifacts", {})  # category -> list of refs
    return session


# ------------------------ Current search parameters ------------------------
def set_current_search(state: Dict[str, Any], *, keywords: str, filters: Optional[Dict[str, Any]] = None, sort_by: Optional[str] = None) -> None:
    session = _ensure_session_dict(state)
    session["current_search"] = {
        "keywords": keywords,
        "filters": filters or {},
        "sort_by": sort_by or "relevant",
    }
    session["timestamps"]["current_search"] = time.time()


def get_current_search(state: Dict[str, Any]) -> Dict[str, Any]:
    session = _ensure_session_dict(state)
    return dict(session.get("current_search", {}))


# ------------------------------ Pagination ---------------------------------
def set_pagination(state: Dict[str, Any], *, page: int, page_size: Optional[int] = None) -> None:
    session = _ensure_session_dict(state)
    pagination = session["pagination"]
    pagination["page"] = max(1, int(page or 1))
    if page_size is not None:
        pagination["page_size"] = max(1, int(page_size))
    session["timestamps"]["pagination"] = time.time()


def get_pagination(state: Dict[str, Any]) -> Dict[str, Any]:
    session = _ensure_session_dict(state)
    return dict(session.get("pagination", {}))


# --------------------------- User preferences ------------------------------
def update_preferences(state: Dict[str, Any], preferences: Dict[str, Any]) -> None:
    session = _ensure_session_dict(state)
    if not isinstance(preferences, dict):
        return
    session["preferences"].update(preferences)
    session["timestamps"]["preferences"] = time.time()


def get_preferences(state: Dict[str, Any]) -> Dict[str, Any]:
    session = _ensure_session_dict(state)
    return dict(session.get("preferences", {}))


# ------------------------- Conversation context ----------------------------
def set_conversation_context(state: Dict[str, Any], context: Dict[str, Any]) -> None:
    session = _ensure_session_dict(state)
    session["context"] = dict(context or {})
    session["timestamps"]["context"] = time.time()


def get_conversation_context(state: Dict[str, Any]) -> Dict[str, Any]:
    session = _ensure_session_dict(state)
    return dict(session.get("context", {}))


def set_last_user_question(state: Dict[str, Any], question: str) -> None:
    """Store the latest user question in conversation context."""
    session = _ensure_session_dict(state)
    ctx = session.setdefault("context", {})
    ctx["last_user_question"] = question or ""
    session["timestamps"]["context"] = time.time()


def get_last_user_question(state: Dict[str, Any]) -> str:
    session = _ensure_session_dict(state)
    return str(session.get("context", {}).get("last_user_question", ""))


# --------------------------- Temporary cart items ---------------------------
def add_cart_item(state: Dict[str, Any], item: Dict[str, Any]) -> None:
    session = _ensure_session_dict(state)
    items: List[Dict[str, Any]] = session["temp_cart"].setdefault("items", [])
    if isinstance(item, dict) and item:
        items.append(item)
        session["timestamps"]["temp_cart"] = time.time()


def remove_cart_item(state: Dict[str, Any], predicate) -> int:
    session = _ensure_session_dict(state)
    items: List[Dict[str, Any]] = session["temp_cart"].setdefault("items", [])
    before = len(items)
    session["temp_cart"]["items"] = [it for it in items if not predicate(it)]
    removed = before - len(session["temp_cart"]["items"])
    if removed:
        session["timestamps"]["temp_cart"] = time.time()
    return removed


def get_cart_items(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    session = _ensure_session_dict(state)
    return list(session.get("temp_cart", {}).get("items", []))


# ------------------------------- Artifacts ---------------------------------
def add_artifact_ref(state: Dict[str, Any], category: str, ref: Dict[str, Any]) -> None:
    session = _ensure_session_dict(state)
    artifacts = session.setdefault("artifacts", {})
    bucket = artifacts.setdefault(category, [])
    bucket.append(ref)
    session["timestamps"][f"artifacts:{category}"] = time.time()

def get_artifact_refs(state: Dict[str, Any], category: str) -> List[Dict[str, Any]]:
    session = _ensure_session_dict(state)
    artifacts = session.get("artifacts", {})
    return list(artifacts.get(category, []))


