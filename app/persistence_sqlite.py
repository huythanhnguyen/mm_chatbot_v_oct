import os
import json
import sqlite3
import threading
import time
from typing import Any, Dict, Optional

_lock = threading.Lock()
_db_path: Optional[str] = None


def init_db(db_path: str) -> None:
    global _db_path
    with _lock:
        if _db_path:
            return
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            # Artifacts index
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    category TEXT,
                    path TEXT,
                    mime_type TEXT,
                    created_at REAL,
                    meta_json TEXT
                )
                """
            )
            # Dialog summaries
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dialogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    user_question TEXT,
                    agent_answer TEXT,
                    intent TEXT,
                    key_info_json TEXT,
                    created_at REAL
                )
                """
            )
            # Searches
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    query TEXT,
                    filters_json TEXT,
                    page INTEGER,
                    total TEXT,
                    search_type TEXT,
                    categories_json TEXT,
                    top_products_json TEXT,
                    created_at REAL
                )
                """
            )
            # Comparisons
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS comparisons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    product_ids_json TEXT,
                    products_json TEXT,
                    created_at REAL
                )
                """
            )
            # Explores
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS explores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    input TEXT,
                    products_json TEXT,
                    created_at REAL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()
        _db_path = db_path


def _conn():
    if not _db_path:
        raise RuntimeError("DB not initialized. Call init_db first.")
    return sqlite3.connect(_db_path)


def save_artifact(session_id: str, category: str, path: str, *, mime_type: str = "application/json", meta: Optional[Dict[str, Any]] = None) -> None:
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO artifacts(session_id, category, path, mime_type, created_at, meta_json) VALUES (?,?,?,?,?,?)",
                (session_id, category, path, mime_type, time.time(), json.dumps(meta or {}, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()


def save_dialog(session_id: str, user_question: str, agent_answer: str, *, intent: str = "", key_info: Optional[Dict[str, Any]] = None) -> None:
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO dialogs(session_id, user_question, agent_answer, intent, key_info_json, created_at) VALUES (?,?,?,?,?,?)",
                (session_id, user_question, agent_answer, intent, json.dumps(key_info or {}, ensure_ascii=False), time.time()),
            )
            conn.commit()
        finally:
            conn.close()


def save_search(session_id: str, query: str, filters: Dict[str, Any], *, page: int, total: str, search_type: str, categories: Dict[str, Any], top_products: Any) -> None:
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO searches(session_id, query, filters_json, page, total, search_type, categories_json, top_products_json, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    query,
                    json.dumps(filters or {}, ensure_ascii=False),
                    int(page),
                    str(total),
                    search_type or "",
                    json.dumps(categories or {}, ensure_ascii=False),
                    json.dumps(top_products or [], ensure_ascii=False),
                    time.time(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def save_comparison(session_id: str, product_ids: Any, products: Any) -> None:
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO comparisons(session_id, product_ids_json, products_json, created_at) VALUES (?,?,?,?)",
                (session_id, json.dumps(product_ids, ensure_ascii=False), json.dumps(products, ensure_ascii=False), time.time()),
            )
            conn.commit()
        finally:
            conn.close()


def save_explore(session_id: str, input_text: str, products: Any) -> None:
    with _lock:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO explores(session_id, input, products_json, created_at) VALUES (?,?,?,?)",
                (session_id, input_text, json.dumps(products, ensure_ascii=False), time.time()),
            )
            conn.commit()
        finally:
            conn.close()


