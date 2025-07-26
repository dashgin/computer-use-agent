"""
Health check API endpoints.
"""

from fastapi import APIRouter

from app.core.logging import get_logger
from app.models.schemas import HealthCheckResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthCheckResponse)
async def health_check():
    """Comprehensive health check endpoint."""
    from app.core.vnc_manager import vnc_manager
    from app.core.websocket_manager import websocket_manager
    from app.db.connection import test_db_connection

    health_status = "healthy"
    components = {}

    # Check database connection
    try:
        db_healthy = await test_db_connection()
        components["database"] = {
            "status": "healthy" if db_healthy else "unhealthy",
            "message": "Database connection successful"
            if db_healthy
            else "Database connection failed",
        }
        if not db_healthy:
            health_status = "degraded"
    except Exception as e:
        components["database"] = {
            "status": "unhealthy",
            "message": f"Database check failed: {str(e)}",
        }
        health_status = "degraded"

    # Check VNC service
    try:
        vnc_health = await vnc_manager.get_health_info()
        components["vnc"] = {
            "status": vnc_health["status"],
            "message": f"VNC server {'running' if vnc_health['server_running'] else 'not running'}",
            "details": {
                "host": vnc_health["host"],
                "port": vnc_health["port"],
                "active_connections": vnc_health["active_connections"],
            },
        }
        if vnc_health["status"] != "healthy":
            health_status = "degraded"
    except Exception as e:
        components["vnc"] = {
            "status": "unhealthy",
            "message": f"VNC health check failed: {str(e)}",
        }
        health_status = "degraded"

    # Check WebSocket manager
    try:
        ws_connections = websocket_manager.get_connection_count()
        components["websocket"] = {
            "status": "healthy",
            "message": "WebSocket manager operational",
            "details": {"active_connections": ws_connections},
        }
    except Exception as e:
        components["websocket"] = {
            "status": "unhealthy",
            "message": f"WebSocket check failed: {str(e)}",
        }
        health_status = "degraded"

    return HealthCheckResponse(
        status=health_status, version="1.0.0", components=components
    ) 