"""
VNC integration REST API endpoints.

This module implements VNC-related REST endpoints including:
- VNC connection information
- VNC server status monitoring
- Session-based VNC authentication
"""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import SessionManagerDep
from app.core.logging import get_logger
from app.core.session_manager import SessionNotFoundError
from app.core.vnc_manager import vnc_manager
from app.models.schemas import VNCConnectionInfo, VNCStatus

logger = get_logger(__name__)

router = APIRouter(prefix="/api/vnc", tags=["vnc"])


@router.get(
    "/connection",
    response_model=VNCConnectionInfo,
    summary="Get VNC connection details",
    description="Get VNC server connection information for accessing the virtual machine",
)
async def get_vnc_connection(
    session_id: str | None = None,
) -> VNCConnectionInfo:
    """
    Get VNC connection information.

    Args:
        session_id: Optional session ID for session-specific authentication

    Returns:
        VNCConnectionInfo: VNC connection details including host, port, and credentials

    Raises:
        HTTPException: If VNC server is not available or connection fails
    """
    try:
        logger.info(f"Getting VNC connection info for session: {session_id}")

        connection_info = await vnc_manager.get_connection_info(session_id)

        logger.info(f"VNC connection info provided for session {session_id}")
        return connection_info

    except RuntimeError as e:
        logger.error(f"VNC server not available: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"VNC server not available: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(f"Failed to get VNC connection info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get VNC connection information",
        ) from e


@router.get(
    "/status",
    response_model=VNCStatus,
    summary="Get VNC server status",
    description="Check the current status and health of the VNC server",
)
async def get_vnc_status() -> VNCStatus:
    """
    Get VNC server status.

    Returns:
        VNCStatus: Current VNC server status including uptime and error information

    Raises:
        HTTPException: If status check fails
    """
    try:
        logger.debug("Checking VNC server status")

        status_info = await vnc_manager.check_server_status()

        logger.debug(
            f"VNC server status: {'running' if status_info.is_running else 'not running'}"
        )
        return status_info

    except Exception as e:
        logger.error(f"Failed to check VNC server status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check VNC server status",
        )


@router.post(
    "/authenticate/{session_id}",
    response_model=dict,
    summary="Authenticate VNC access for session",
    description="Authenticate VNC access for a specific session",
)
async def authenticate_vnc_access(
    session_id: str, session_manager: SessionManagerDep
) -> dict:
    """
    Authenticate VNC access for a session.

    Args:
        session_id: The session ID requesting VNC access
        session_manager: Session manager dependency

    Returns:
        dict: Authentication result

    Raises:
        HTTPException: If session not found or authentication fails
    """
    try:
        logger.info(f"Authenticating VNC access for session: {session_id}")

        # Verify session exists
        try:
            await session_manager.get_session(session_id)
        except SessionNotFoundError:
            logger.warning(f"Session not found for VNC authentication: {session_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        # Authenticate VNC access
        authenticated = await vnc_manager.authenticate_connection(session_id)

        if not authenticated:
            logger.warning(f"VNC authentication failed for session: {session_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="VNC authentication failed",
            )

        logger.info(f"VNC authentication successful for session: {session_id}")
        return {
            "session_id": session_id,
            "authenticated": True,
            "message": "VNC access authenticated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"VNC authentication error for session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="VNC authentication failed",
        )


@router.delete(
    "/disconnect/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect VNC access for session",
    description="Disconnect VNC access for a specific session",
)
async def disconnect_vnc_access(session_id: str, session_manager: SessionManagerDep):
    """
    Disconnect VNC access for a session.

    Args:
        session_id: The session ID to disconnect VNC access for
        session_manager: Session manager dependency

    Raises:
        HTTPException: If session not found or disconnection fails
    """
    try:
        logger.info(f"Disconnecting VNC access for session: {session_id}")

        # Verify session exists
        try:
            await session_manager.get_session(session_id)
        except SessionNotFoundError:
            logger.warning(f"Session not found for VNC disconnection: {session_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        # Disconnect VNC access
        disconnected = await vnc_manager.disconnect_session(session_id)

        if not disconnected:
            logger.warning(f"VNC disconnection failed for session: {session_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="VNC disconnection failed",
            )

        logger.info(f"VNC access disconnected for session: {session_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"VNC disconnection error for session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="VNC disconnection failed",
        )


@router.get(
    "/connections",
    response_model=dict,
    summary="Get active VNC connections",
    description="Get information about currently active VNC connections",
)
async def get_active_vnc_connections() -> dict:
    """
    Get active VNC connections information.

    Returns:
        dict: Information about active VNC connections

    Raises:
        HTTPException: If connection information retrieval fails
    """
    try:
        logger.debug("Getting active VNC connections")

        active_sessions = await vnc_manager.get_active_sessions()
        connection_count = await vnc_manager.get_connection_count()

        response = {
            "total_connections": connection_count,
            "active_sessions": list(active_sessions),
            "session_count": len(active_sessions),
        }

        logger.debug(f"Active VNC connections: {connection_count}")
        return response

    except Exception as e:
        logger.error(f"Failed to get active VNC connections: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get VNC connection information",
        )


@router.get(
    "/health",
    response_model=dict,
    summary="Get VNC service health",
    description="Get comprehensive health information about the VNC service",
)
async def get_vnc_health() -> dict:
    """
    Get VNC service health information.

    Returns:
        dict: Comprehensive VNC service health information

    Raises:
        HTTPException: If health check fails
    """
    try:
        logger.debug("Getting VNC service health information")

        health_info = await vnc_manager.get_health_info()

        logger.debug(f"VNC service health: {health_info['status']}")
        return health_info

    except Exception as e:
        logger.error(f"Failed to get VNC service health: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get VNC service health information",
        )
