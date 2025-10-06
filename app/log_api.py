"""
API endpoints để serve logs và analytics data
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
import asyncio
from app.agent_analytics import AgentAnalytics, estimate_cost_from_analytics

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="MMVN Agent Log Viewer", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global analytics instance
analytics = AgentAnalytics()

# WebSocket connections for real-time updates
active_connections: List[WebSocket] = []

@app.get("/")
async def root():
    """Serve the main log viewer page"""
    return FileResponse("log_viewer.html")

@app.get("/api/analytics")
async def get_analytics(
    hours_back: int = Query(24, description="Hours to look back for analytics")
):
    """Get analytics data"""
    try:
        data = analytics.parse_logs(hours_back)
        
        # Add cost estimation
        if "error" not in data:
            cost_estimate = estimate_cost_from_analytics(data)
            data["cost_estimate"] = cost_estimate
        
        return data
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def get_logs(
    hours_back: int = Query(24, description="Hours to look back"),
    limit: int = Query(100, description="Maximum number of logs to return"),
    log_type: Optional[str] = Query(None, description="Filter by log type"),
    session_id: Optional[str] = Query(None, description="Filter by session ID")
):
    """Get raw log entries"""
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        logs = []
        
        if not os.path.exists(analytics.log_file):
            return {"logs": [], "total": 0}
        
        with open(analytics.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if "AGENT_INTERACTION:" in line or "TOOL_USAGE:" in line or "TOOL_COMPLETION:" in line or "TOOL_ERROR:" in line:
                    try:
                        json_start = line.find('{')
                        if json_start != -1:
                            log_data = json.loads(line[json_start:])
                            timestamp = datetime.fromtimestamp(log_data.get('timestamp', 0))
                            
                            if timestamp < cutoff_time:
                                continue
                            
                            # Apply filters
                            if log_type and log_data.get('type') != log_type:
                                continue
                            
                            if session_id and log_data.get('data', {}).get('session_id') != session_id:
                                continue
                            
                            logs.append(log_data)
                            
                            if len(logs) >= limit:
                                break
                                
                    except json.JSONDecodeError:
                        continue
        
        # Sort by timestamp (newest first)
        logs.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return {
            "logs": logs,
            "total": len(logs),
            "filters": {
                "hours_back": hours_back,
                "log_type": log_type,
                "session_id": session_id
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions")
async def get_sessions(
    hours_back: int = Query(24, description="Hours to look back")
):
    """Get session information"""
    try:
        data = analytics.parse_logs(hours_back)
        sessions = {}
        
        for session_id, session_logs in analytics.sessions.items():
            if session_logs:
                start_time = min(log.get('timestamp', 0) for log in session_logs)
                end_time = max(log.get('timestamp', 0) for log in session_logs)
                
                # Count interactions by type
                interaction_counts = {}
                total_tokens = 0
                
                for log in session_logs:
                    log_type = log.get('type', 'unknown')
                    interaction_counts[log_type] = interaction_counts.get(log_type, 0) + 1
                    total_tokens += log.get('tokens', 0)
                
                sessions[session_id] = {
                    "session_id": session_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": end_time - start_time,
                    "interaction_count": len(session_logs),
                    "interaction_types": interaction_counts,
                    "total_tokens": total_tokens,
                    "last_activity": end_time
                }
        
        # Sort by last activity
        sorted_sessions = sorted(sessions.values(), key=lambda x: x['last_activity'], reverse=True)
        
        return {
            "sessions": sorted_sessions,
            "total_sessions": len(sorted_sessions)
        }
        
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/log-types")
async def get_log_types():
    """Get available log types"""
    return {
        "log_types": [
            "INPUT_RECEIVED",
            "MEMORY_SEARCH", 
            "PROMPT_ENHANCED",
            "LLM_RESPONSE",
            "SESSION_SUMMARY",
            "AGENT_ERROR",
            "TOOL_USAGE",
            "TOOL_COMPLETION",
            "TOOL_ERROR"
        ]
    }

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time log updates"""
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        while True:
            # Send periodic updates
            await asyncio.sleep(5)
            
            # Get latest logs
            latest_logs = await get_logs(hours_back=1, limit=10)
            
            # Create a clean data structure for WebSocket
            websocket_data = {
                "logs": latest_logs.get("logs", []),
                "total": latest_logs.get("total", 0)
            }
            
            await websocket.send_json({
                "type": "log_update",
                "data": websocket_data
            })
            
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)

@app.get("/api/export/logs")
async def export_logs(
    hours_back: int = Query(24, description="Hours to look back"),
    format: str = Query("json", description="Export format: json or csv")
):
    """Export logs in various formats"""
    try:
        logs_data = await get_logs(hours_back=hours_back, limit=10000)
        logs = logs_data["logs"]
        
        if format == "json":
            return {
                "logs": logs,
                "exported_at": datetime.now().isoformat(),
                "total_logs": len(logs)
            }
        elif format == "csv":
            # Convert to CSV format
            csv_lines = ["timestamp,type,session_id,tokens,data"]
            
            for log in logs:
                timestamp = datetime.fromtimestamp(log.get('timestamp', 0)).isoformat()
                log_type = log.get('type', '')
                session_id = log.get('data', {}).get('session_id', '')
                tokens = log.get('tokens', 0)
                data_str = json.dumps(log.get('data', {}), ensure_ascii=False).replace('"', '""')
                
                csv_lines.append(f'"{timestamp}","{log_type}","{session_id}",{tokens},"{data_str}"')
            
            csv_content = "\n".join(csv_lines)
            
            return {
                "content": csv_content,
                "exported_at": datetime.now().isoformat(),
                "total_logs": len(logs),
                "format": "csv"
            }
        else:
            raise HTTPException(status_code=400, detail="Unsupported format")
            
    except Exception as e:
        logger.error(f"Error exporting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "log_file_exists": os.path.exists(analytics.log_file),
        "active_connections": len(active_connections)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
