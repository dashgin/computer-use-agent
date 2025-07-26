"""
VNC integration manager for connection management and monitoring.

This module provides the VNCManager class that handles VNC server connection
management, status monitoring, authentication, and multi-user session scenarios.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from ..core.config import settings
from ..models.schemas import VNCConnectionInfo, VNCStatus

logger = logging.getLogger(__name__)


class VNCManager:
    """
    Manages VNC server connections, authentication, and monitoring.

    This class provides functionality for:
    - VNC server connection management
    - Status monitoring and health checks
    - Authentication and access control
    - Multi-user session handling
    """

    def __init__(self):
        """Initialize the VNC manager with configuration settings."""
        self.host = settings.VNC_HOST
        self.port = settings.VNC_PORT
        self.password = settings.VNC_PASSWORD
        self.display = ":1"  # Default display from Docker setup

        # Track active sessions and their VNC access
        self._active_sessions: set[str] = set()
        self._session_connections: dict[str, datetime] = {}

        # Connection monitoring
        self._last_health_check: Optional[datetime] = None
        self._server_status: Optional[VNCStatus] = None
        self._health_check_interval = 30  # seconds

        logger.info(f"VNC Manager initialized - Host: {self.host}, Port: {self.port}")

    async def get_connection_info(
        self, session_id: Optional[str] = None
    ) -> VNCConnectionInfo:
        """
        Get VNC connection information for a session.

        Args:
            session_id: Optional session ID for session-specific authentication

        Returns:
            VNCConnectionInfo: Connection details including host, port, and status

        Raises:
            RuntimeError: If VNC server is not available
        """
        logger.info(f"Getting VNC connection info for session: {session_id}")

        # Check server status first
        status = await self.check_server_status()

        if not status.is_running:
            error_msg = f"VNC server is not running: {status.error_message}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from None

        # Track session access if provided
        if session_id:
            await self._track_session_access(session_id)

        connection_info = VNCConnectionInfo(
            host=self.host,
            port=self.port,
            password=self.password,
            display=self.display,
            status="connected" if status.is_running else "disconnected",
        )

        logger.info(
            f"VNC connection info provided for session {session_id}: {self.host}:{self.port}"
        )
        return connection_info

    async def check_server_status(self) -> VNCStatus:
        """
        Check VNC server status and health.

        Returns:
            VNCStatus: Current server status including uptime and error information
        """
        current_time = datetime.now(timezone.utc)

        # Use cached status if recent health check
        if (
            self._last_health_check
            and self._server_status
            and (current_time - self._last_health_check).total_seconds()
            < self._health_check_interval
        ):
            return self._server_status

        logger.debug("Performing VNC server health check")

        try:
            # Check if VNC port is accessible
            is_running = await self._check_port_accessible(self.host, self.port)

            if is_running:
                # Get additional server information
                uptime = await self._get_server_uptime()

                self._server_status = VNCStatus(
                    is_running=True,
                    display=self.display,
                    port=self.port,
                    uptime=uptime,
                    error_message=None,
                )
                logger.debug(
                    f"VNC server is running - Port: {self.port}, Uptime: {uptime}s"
                )
            else:
                self._server_status = VNCStatus(
                    is_running=False,
                    display=None,
                    port=None,
                    uptime=None,
                    error_message=f"VNC server not accessible on {self.host}:{self.port}",
                )
                logger.warning(f"VNC server not accessible on {self.host}:{self.port}")

        except Exception as e:  # pylint: disable=broad-exception-caught
            error_msg = f"Error checking VNC server status: {str(e)}"
            logger.error(error_msg)

            self._server_status = VNCStatus(
                is_running=False,
                display=None,
                port=None,
                uptime=None,
                error_message=error_msg,
            )

        self._last_health_check = current_time
        return self._server_status

    async def authenticate_connection(self, session_id: str) -> bool:
        """
        Authenticate a VNC connection for a specific session.

        Args:
            session_id: Session ID requesting VNC access

        Returns:
            bool: True if authentication successful, False otherwise
        """
        logger.info(f"Authenticating VNC connection for session: {session_id}")

        try:
            # Check if VNC server is running
            status = await self.check_server_status()
            if not status.is_running:
                logger.warning(
                    f"VNC authentication failed - server not running for session: {session_id}"
                )
                return False

            # For now, we allow all sessions to access VNC
            # In a production environment, you might want to implement
            # more sophisticated authentication logic here

            # Track the authenticated session
            await self._track_session_access(session_id)

            logger.info(f"VNC authentication successful for session: {session_id}")
            return True

        except Exception as e:
            logger.error(f"VNC authentication error for session {session_id}: {str(e)}")
            return False

    async def get_active_sessions(self) -> set[str]:
        """
        Get list of sessions currently accessing VNC.

        Returns:
            set[str]: set of active session IDs
        """
        # Clean up old sessions (older than 1 hour)
        current_time = datetime.now(timezone.utc)
        expired_sessions = {
            session_id
            for session_id, last_access in self._session_connections.items()
            if (current_time - last_access).total_seconds() > 3600
        }

        for session_id in expired_sessions:
            await self._remove_session_access(session_id)

        return self._active_sessions.copy()

    async def disconnect_session(self, session_id: str) -> bool:
        """
        Disconnect a specific session from VNC access.

        Args:
            session_id: Session ID to disconnect

        Returns:
            bool: True if disconnection successful, False otherwise
        """
        logger.info(f"Disconnecting VNC access for session: {session_id}")

        try:
            await self._remove_session_access(session_id)
            logger.info(f"VNC access disconnected for session: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error disconnecting VNC for session {session_id}: {str(e)}")
            return False

    async def get_connection_count(self) -> int:
        """
        Get the number of active VNC connections.

        Returns:
            int: Number of active connections
        """
        active_sessions = await self.get_active_sessions()
        return len(active_sessions)

    async def _check_port_accessible(
        self, host: str, port: int, timeout: float = 5.0
    ) -> bool:
        """
        Check if a port is accessible on the given host.

        Args:
            host: Host to check
            port: Port to check
            timeout: Connection timeout in seconds

        Returns:
            bool: True if port is accessible, False otherwise
        """
        try:
            # Use asyncio to create a connection with timeout
            future = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(future, timeout=timeout)

            # Close the connection
            writer.close()
            await writer.wait_closed()

            return True

        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return False
        except Exception as e:
            logger.debug(f"Unexpected error checking port {host}:{port}: {str(e)}")
            return False

    async def _get_server_uptime(self) -> Optional[int]:
        """
        Get VNC server uptime in seconds.

        Returns:
            Optional[int]: Uptime in seconds, None if unable to determine
        """
        try:
            # Try to get process information using netstat
            process = await asyncio.create_subprocess_exec(
                "netstat",
                "-tulpn",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode("utf-8")
                # Look for VNC port in netstat output
                for line in output.split("\n"):
                    if f":{self.port}" in line and "LISTEN" in line:
                        # For simplicity, return a placeholder uptime
                        # In a real implementation, you might parse process start time
                        return 3600  # 1 hour placeholder

            return None

        except Exception as e:
            logger.debug(f"Error getting VNC server uptime: {str(e)}")
            return None

    async def _track_session_access(self, session_id: str) -> None:
        """
        Track VNC access for a session.

        Args:
            session_id: Session ID to track
        """
        current_time = datetime.now(timezone.utc)

        self._active_sessions.add(session_id)
        self._session_connections[session_id] = current_time

        logger.debug(f"Tracking VNC access for session: {session_id}")

    async def _remove_session_access(self, session_id: str) -> None:
        """
        Remove VNC access tracking for a session.

        Args:
            session_id: Session ID to remove
        """
        self._active_sessions.discard(session_id)
        self._session_connections.pop(session_id, None)

        logger.debug(f"Removed VNC access tracking for session: {session_id}")

    async def get_health_info(self) -> dict[str, any]:
        """
        Get comprehensive health information about the VNC service.

        Returns:
            dict[str, any]: Health information including status, connections, and metrics
        """
        status = await self.check_server_status()
        active_sessions = await self.get_active_sessions()

        return {
            "status": "healthy" if status.is_running else "unhealthy",
            "server_running": status.is_running,
            "host": self.host,
            "port": self.port,
            "display": status.display,
            "uptime_seconds": status.uptime,
            "active_connections": len(active_sessions),
            "active_sessions": list(active_sessions),
            "last_health_check": self._last_health_check.isoformat()
            if self._last_health_check
            else None,
            "error_message": status.error_message,
        }


# Global VNC manager instance
vnc_manager = VNCManager()
