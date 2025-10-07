"""
Runner configuration for MMVN Agent with Memory
Ensures proper memory service integration + background persistence hooks
"""

import logging
import threading
from collections import deque
from typing import Optional, Dict, Any
import time
import sqlite3
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from memory_config import get_session_service, get_memory_service
from .persistence_sqlite import init_db, save_dialog
from app.tools.artifact_tools import write_json_artifact
from app.tools.session_state import SESSION_ROOT_KEY

logger = logging.getLogger(__name__)


# ---------------- Background persistence queue (non-blocking) ----------------
_persist_queue: deque = deque()
_worker_started = False
_worker_lock = threading.Lock()

# ------------------------- EWMA latency tracking ---------------------------
_ewma_latency_seconds: Optional[float] = None
_ewma_alpha: float = 0.3  # smoothing factor
_total_runs: int = 0


def _start_worker():
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return

        def _worker_loop():
            while True:
                try:
                    item = None
                    try:
                        item = _persist_queue.popleft()
                    except IndexError:
                        # Sleep lightly to avoid busy wait
                        threading.Event().wait(0.1)
                        continue
                    if not item:
                        continue
                    if item.get("type") == "dialog_summary":
                        _handle_dialog_summary_item(item)
                except Exception as e:
                    logger.warning(f"Persist worker error: {e}")

        t = threading.Thread(target=_worker_loop, name="persist-worker", daemon=True)
        t.start()
        _worker_started = True
        logger.info("Background persist worker started")


def _handle_dialog_summary_item(item: Dict[str, Any]):
    session_id = item.get("session_id", "unknown")
    payload = {
        "type": "dialog_summary",
        "user_question": item.get("user_question", ""),
        "agent_answer": item.get("agent_answer", ""),
        "intent": item.get("intent", ""),
        "key_info": item.get("key_info", {})
    }
    try:
        path = write_json_artifact(payload, category="dialog", session_id=session_id)
        save_dialog(session_id, payload["user_question"], payload["agent_answer"], intent=payload["intent"], key_info=payload["key_info"]) 
        logger.info("Persisted dialog summary (bg)")
    except Exception as e:
        logger.warning(f"Persist dialog failed: {e}")


def enqueue_dialog_summary(session_id: str, user_question: str, agent_answer: str = "", intent: str = "", key_info: Optional[Dict[str, Any]] = None):
    """Fire-and-forget enqueue of dialog summary to be saved in background."""
    _persist_queue.append({
        "type": "dialog_summary",
        "session_id": session_id or "unknown",
        "user_question": user_question or "",
        "agent_answer": agent_answer or "",
        "intent": intent or "",
        "key_info": key_info or {},
    })


def _update_ewma_latency(elapsed_seconds: float) -> None:
    global _ewma_latency_seconds, _total_runs
    _total_runs += 1
    if _ewma_latency_seconds is None:
        _ewma_latency_seconds = elapsed_seconds
    else:
        _ewma_latency_seconds = _ewma_alpha * elapsed_seconds + (1 - _ewma_alpha) * _ewma_latency_seconds


def log_ewma_latency():
    if _ewma_latency_seconds is not None:
        logger.info(f"Latency EWMA: { _ewma_latency_seconds:.3f}s over {_total_runs} runs")
    else:
        logger.info("Latency EWMA: no runs yet")


def log_db_counts(db_path: str = "data/mmvn_runner.sqlite3"):
    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            tables = ["artifacts", "dialogs", "searches", "comparisons", "explores"]
            counts: Dict[str, int] = {}
            for t in tables:
                try:
                    cur.execute(f"SELECT COUNT(1) FROM {t}")
                    row = cur.fetchone()
                    counts[t] = int(row[0]) if row else 0
                except Exception:
                    counts[t] = -1
            logger.info(f"SQLite counts: {counts}")
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"SQLite count failed: {e}")

def create_memory_runner(agent, app_name: str = "mmvn_app"):
    """
    Create a Runner with proper memory service configuration.
    
    Args:
        agent: The agent to run
        app_name: Application name for session management
    
    Returns:
        Configured Runner instance
    """
    try:
        # Init SQLite persistence (creates DB and tables once) and worker
        try:
            init_db(db_path="data/mmvn_runner.sqlite3")
            logger.info("SQLite DB initialized at data/mmvn_runner.sqlite3")
            _start_worker()
        except Exception as e:
            logger.warning(f"SQLite init failed: {e}")

        # Get shared services
        session_service = get_session_service()
        memory_service = get_memory_service()
        
        # Create runner with memory service
        runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service,
            memory_service=memory_service
        )
        
        logger.info(f"Created memory-enabled runner for app: {app_name}")
        return runner
        
    except Exception as e:
        logger.error(f"Error creating memory runner: {e}")
        # Fallback to basic runner
        return Runner(
            agent=agent,
            app_name=app_name
        )

def add_session_to_memory(runner, user_id: str, session_id: str):
    """
    Add a completed session to memory.
    This should be called when a session is complete.
    
    Args:
        runner: The runner instance
        user_id: User ID
        session_id: Session ID
    """
    try:
        # Get the completed session
        completed_session = runner.session_service.get_session(
            app_name=runner.app_name,
            user_id=user_id,
            session_id=session_id
        )
        
        # Add to memory
        runner.memory_service.add_session_to_memory(completed_session)
        logger.info(f"Added session {session_id} to memory for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error adding session to memory: {e}")

async def run_with_memory(agent, user_id: str, session_id: str, user_message, app_name: str = "mmvn_app"):
    """
    Run agent with automatic memory integration.
    
    Args:
        agent: The agent to run
        user_id: User ID
        session_id: Session ID
        user_message: User message
        app_name: Application name
    
    Returns:
        Agent response
    """
    try:
        # Create memory-enabled runner
        runner = create_memory_runner(agent, app_name)
        
        # Create session if not exists
        try:
            await runner.session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
        except:
            # Session might already exist
            pass
        
        # Pre-input hook: enqueue dialog summary (input-only) non-blocking
        try:
            enqueue_dialog_summary(session_id, user_message)
        except Exception:
            pass

        # Run the agent
        response = None
        _t0 = time.time()
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                response = event.content.parts[0].text
                break
        elapsed = max(0.0, time.time() - _t0)
        try:
            _update_ewma_latency(elapsed)
            logger.info(f"End-to-end latency: {elapsed:.3f}s")
            log_ewma_latency()
        except Exception:
            pass
        
        # Post-response hook: enqueue full dialog summary (non-blocking)
        try:
            enqueue_dialog_summary(session_id, user_message, agent_answer=response or "")
        except Exception:
            pass

        # Add session to memory after completion
        add_session_to_memory(runner, user_id, session_id)

        # Quick DB counts log
        try:
            log_db_counts()
        except Exception:
            pass
        
        return response
        
    except Exception as e:
        logger.error(f"Error running agent with memory: {e}")
        return f"Lỗi khi chạy agent: {str(e)}"
