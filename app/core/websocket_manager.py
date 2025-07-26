"""
WebSocket manager for real-time communication.

This module implements the WebSocketManager class that provides WebSocket connection
lifecycle management, real-time message broadcasting, connection state management,
and progress update streaming functionality.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import WebSocket
from pydantic import ValidationError

from app.core.logging import get_logger
from app.models.schemas import (
    ProgressUpdate,
    SessionStatus,
    UpdateType,
    WebSocketMessage,
)

logger = get_logger(__name__)


class WebSocketConnectionError(Exception):
    """Raised when WebSocket connection operations fail."""


class WebSocketAuthenticationError(Exception):
    """Raised when WebSocket authentication fails."""


class WebSocketConnection:
    """
    Represents a single WebSocket connection with metadata.
    """

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        connection_id: Optional[str] = None,
        client_info: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize a WebSocket connection.

        Args:
            websocket: The FastAPI WebSocket instance
            session_id: Associated session ID
            connection_id: Unique connection identifier
            client_info: Optional client metadata
        """
        self.websocket = websocket
        self.session_id = session_id
        self.connection_id = connection_id or str(uuid.uuid4())
        self.client_info = client_info or {}
        self.connected_at = datetime.now(timezone.utc)
        self.last_ping = datetime.now(timezone.utc)
        self.is_active = True

    async def send_message(self, message: dict[str, Any]) -> bool:
        """
        Send a message through the WebSocket connection.

        Args:
            message: Message dictionary to send

        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        if not self.is_active:
            logger.debug(f"Connection {self.connection_id} is marked as inactive")
            return False

        try:
            await self.websocket.send_json(message)
            logger.debug(
                f"Successfully sent message to connection {self.connection_id}"
            )
            return True
        except ConnectionResetError as e:
            logger.warning(f"Connection reset for {self.connection_id}: {str(e)}")
            self.is_active = False
            return False
        except Exception as e:
            logger.warning(
                f"Failed to send message to connection {self.connection_id}: {str(e)} (type: {type(e).__name__})"
            )
            # Don't mark as inactive immediately - could be temporary issue
            # Only mark inactive for connection-related errors
            if "connection" in str(e).lower() or "socket" in str(e).lower():
                self.is_active = False
            return False

    async def send_text(self, text: str) -> bool:
        """
        Send a text message through the WebSocket connection.

        Args:
            text: Text message to send

        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        if not self.is_active:
            return False

        try:
            await self.websocket.send_text(text)
            return True
        except Exception as e:
            logger.warning(
                f"Failed to send text to connection {self.connection_id}: {str(e)}"
            )
            self.is_active = False
            return False

    async def close(self, code: int = 1000, reason: str = "Connection closed") -> None:
        """
        Close the WebSocket connection.

        Args:
            code: WebSocket close code
            reason: Close reason
        """
        try:
            if self.is_active:
                await self.websocket.close(code=code, reason=reason)
        except Exception as e:
            logger.warning(f"Error closing connection {self.connection_id}: {str(e)}")
        finally:
            self.is_active = False

    def update_ping(self) -> None:
        """Update the last ping timestamp."""
        self.last_ping = datetime.now(timezone.utc)


class WebSocketManager:
    """
    Manages WebSocket connections for real-time communication.

    This class provides comprehensive WebSocket management including:
    - Connection lifecycle management (connect, disconnect, cleanup)
    - Real-time message broadcasting to connected clients
    - Connection state management and health monitoring
    - Progress update streaming functionality
    - Session-based connection grouping
    """

    def __init__(self):
        """Initialize the WebSocketManager."""
        self._connections: dict[str, WebSocketConnection] = {}
        self._session_connections: dict[str, set[str]] = {}
        self._connection_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._ping_interval = 30  # seconds
        self._connection_timeout = 300  # 5 minutes
        self._initialized = False

        logger.info("WebSocketManager initialized")

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        client_info: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Accept and register a new WebSocket connection.

        Args:
            websocket: The FastAPI WebSocket instance
            session_id: Associated session ID
            client_info: Optional client metadata

        Returns:
            str: Connection ID for the new connection

        Raises:
            WebSocketConnectionError: If connection setup fails
        """
        # Initialize cleanup task on first connection if not already done
        if not self._initialized:
            self._start_cleanup_task()
            self._initialized = True

        try:
            # Accept the WebSocket connection
            await websocket.accept()

            # Create connection object
            connection = WebSocketConnection(
                websocket=websocket, session_id=session_id, client_info=client_info
            )

            async with self._connection_lock:
                # Register connection
                self._connections[connection.connection_id] = connection

                # Add to session group
                if session_id not in self._session_connections:
                    self._session_connections[session_id] = set()
                self._session_connections[session_id].add(connection.connection_id)

            logger.info(
                f"WebSocket connected - Connection: {connection.connection_id}, "
                f"Session: {session_id}, Client: {client_info}"
            )

            # Send welcome message directly via websocket to avoid marking as inactive
            try:
                welcome_message = {
                    "type": "connection_established",
                    "session_id": session_id,
                    "connection_id": connection.connection_id,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                }
                await websocket.send_json(welcome_message)
                logger.debug(
                    f"Welcome message sent to connection {connection.connection_id}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to send welcome message to {connection.connection_id}: {e}"
                )
                # Don't fail the connection setup for this

            return connection.connection_id

        except Exception as e:
            logger.error(
                f"Failed to establish WebSocket connection for session {session_id}: {str(e)}"
            )
            raise WebSocketConnectionError(f"Connection setup failed: {str(e)}")

    async def disconnect(
        self, connection_id: str, code: int = 1000, reason: str = "Normal closure"
    ) -> bool:
        """
        Disconnect and cleanup a WebSocket connection.

        Args:
            connection_id: Connection ID to disconnect
            code: WebSocket close code
            reason: Disconnect reason

        Returns:
            bool: True if connection was found and disconnected, False otherwise
        """

        async with self._connection_lock:
            connection = self._connections.get(connection_id)
            if not connection:
                logger.warning(
                    f"Attempted to disconnect non-existent connection: {connection_id}"
                )
                return False

            # Close the WebSocket
            await connection.close(code=code, reason=reason)

            # Remove from connections
            # del self._connections[connection_id]

            # Remove from session group
            session_connections = self._session_connections.get(
                connection.session_id, set()
            )
            session_connections.discard(connection_id)

            # Clean up empty session groups
            if not session_connections:
                self._session_connections.pop(connection.session_id, None)

            logger.info(
                f"WebSocket disconnected - Connection: {connection_id}, "
                f"Session: {connection.session_id}, Reason: {reason}"
            )

            return True

    async def broadcast_to_session(
        self, session_id: str, message: dict[str, Any]
    ) -> int:
        """
        Broadcast a message to all connections in a session.

        Args:
            session_id: Session ID to broadcast to
            message: Message dictionary to broadcast

        Returns:
            int: Number of connections that received the message successfully
        """

        connection_ids = self._session_connections.get(session_id, set()).copy()

        if not connection_ids:
            logger.debug(f"No active connections for session {session_id}")
            return 0

        successful_sends = 0
        failed_connections = []

        # Send to all connections - simplified approach like the working version
        for connection_id in connection_ids:
            connection = self._connections.get(connection_id)
            if connection:
                try:
                    # Try to send the message directly
                    await connection.websocket.send_json(message)
                    successful_sends += 1
                    logger.debug(
                        f"Successfully sent message to connection {connection_id}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send to connection {connection_id}: {e}")
                    connection.is_active = False
                    failed_connections.append(connection_id)
            else:
                failed_connections.append(connection_id)

        # Clean up failed connections
        if failed_connections:
            await self._cleanup_failed_connections(failed_connections)

        logger.debug(
            f"Broadcast to session {session_id}: {successful_sends}/{len(connection_ids)} successful"
        )

        return successful_sends

    async def send_to_session(
        self, session_id: str, message_type: str, content: str = None, **kwargs
    ) -> int:
        """
        Send a typed message to all connections in a session (like the working version).

        Args:
            session_id: Session ID to send to
            message_type: Type of message (e.g., 'agent_message', 'tool_use', 'tool_result', etc.)
            content: Message content
            **kwargs: Additional message data
        Returns:
            int: Number of connections that received the message successfully
        """
        message = {
            "type": message_type,
            "session_id": session_id,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }

        return await self.broadcast_to_session(session_id, message)

    async def send_progress_update(
        self, session_id: str, update: ProgressUpdate
    ) -> int:
        """
        Send a progress update to all connections in a session.

        Args:
            session_id: Session ID to send update to
            update: Progress update object

        Returns:
            int: Number of connections that received the update successfully
        """

        try:
            # Validate the progress update and serialize datetime objects properly
            update_dict = update.model_dump(mode="json")

            # Wrap in WebSocket message format
            ws_message = WebSocketMessage(type="progress_update", payload=update_dict)

            return await self.broadcast_to_session(
                session_id, ws_message.model_dump(mode="json")
            )

        except ValidationError as e:
            logger.error(f"Invalid progress update for session {session_id}: {str(e)}")
            return 0
        except Exception as e:
            logger.error(
                f"Failed to send progress update to session {session_id}: {str(e)}"
            )
            return 0

    async def send_message_update(
        self,
        session_id: str,
        message_content: str,
        role: str = "assistant",
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Send a message update to all connections in a session.

        Args:
            session_id: Session ID to send update to
            message_content: Message content
            role: Message role (user, assistant, tool)
            metadata: Optional message metadata

        Returns:
            int: Number of connections that received the update successfully
        """

        update = ProgressUpdate(
            type=UpdateType.MESSAGE,
            data={"role": role, "content": message_content, "metadata": metadata or {}},
            session_id=session_id,
        )

        return await self.send_progress_update(session_id, update)

    async def send_tool_start_update(
        self,
        session_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
    ) -> int:
        """
        Send a tool execution start update to all connections in a session.

        Args:
            session_id: Session ID to send update to
            tool_name: Name of the tool being executed
            tool_input: Tool input parameters
            tool_use_id: Unique tool use identifier

        Returns:
            int: Number of connections that received the update successfully
        """

        update = ProgressUpdate(
            type=UpdateType.TOOL_START,
            data={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_use_id": tool_use_id,
            },
            session_id=session_id,
        )

        return await self.send_progress_update(session_id, update)

    async def send_tool_complete_update(
        self,
        session_id: str,
        tool_name: str,
        tool_output: dict[str, Any],
        tool_use_id: str,
        success: bool = True,
    ) -> int:
        """
        Send a tool execution completion update to all connections in a session.

        Args:
            session_id: Session ID to send update to
            tool_name: Name of the tool that was executed
            tool_output: Tool output results
            tool_use_id: Unique tool use identifier
            success: Whether the tool execution was successful

        Returns:
            int: Number of connections that received the update successfully
        """

        update = ProgressUpdate(
            type=UpdateType.TOOL_COMPLETE,
            data={
                "tool_name": tool_name,
                "tool_output": tool_output,
                "tool_use_id": tool_use_id,
                "success": success,
            },
            session_id=session_id,
        )

        return await self.send_progress_update(session_id, update)

    async def send_error_update(
        self,
        session_id: str,
        error_message: str,
        error_code: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Send an error update to all connections in a session.

        Args:
            session_id: Session ID to send update to
            error_message: Error message
            error_code: Optional error code
            context: Optional error context

        Returns:
            int: Number of connections that received the update successfully
        """

        update = ProgressUpdate(
            type=UpdateType.ERROR,
            data={
                "error_message": error_message,
                "error_code": error_code,
                "context": context or {},
            },
            session_id=session_id,
        )

        return await self.send_progress_update(session_id, update)

    async def send_session_status_update(
        self,
        session_id: str,
        status: SessionStatus,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Send a session status update to all connections in a session.

        Args:
            session_id: Session ID to send update to
            status: New session status
            metadata: Optional status metadata

        Returns:
            int: Number of connections that received the update successfully
        """

        update = ProgressUpdate(
            type=UpdateType.SESSION_STATUS,
            data={"status": status.value, "metadata": metadata or {}},
            session_id=session_id,
        )

        return await self.send_progress_update(session_id, update)

    async def handle_client_message(
        self,
        connection_id: str,
        message: str,
        message_handler: Optional[Callable] = None,
    ) -> bool:
        """
        Handle an incoming message from a WebSocket client.

        Args:
            connection_id: Connection ID that sent the message
            message: Raw message string
            message_handler: Optional callback to handle the parsed message

        Returns:
            bool: True if message was handled successfully, False otherwise
        """

        connection = self._connections.get(connection_id)
        if not connection or not connection.is_active:
            logger.warning(
                f"Received message from inactive connection: {connection_id}"
            )
            # return False

        try:
            # Parse message
            message_data = json.loads(message)

            # Update connection ping
            connection.update_ping()

            # Handle ping messages
            if message_data.get("type") == "ping":
                pong_message = WebSocketMessage(
                    type="pong",
                    payload={"server_time": datetime.now(timezone.utc).isoformat()},
                )
                await connection.send_message(pong_message.model_dump(mode="json"))
                return True

            # Call message handler if provided
            if message_handler:
                try:
                    await message_handler(
                        connection.session_id, message_data, connection_id
                    )
                except Exception as e:
                    logger.error(
                        f"Message handler failed for connection {connection_id}: {str(e)}"
                    )
                    # Send error back to client
                    error_message = WebSocketMessage(
                        type="error",
                        payload={
                            "error_message": "Message processing failed",
                            "error_code": "MESSAGE_HANDLER_ERROR",
                        },
                    )
                    await connection.send_message(error_message.model_dump(mode="json"))
                    return False

            return True

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON from connection {connection_id}: {str(e)}")
            # Send error back to client
            error_message = WebSocketMessage(
                type="error",
                payload={
                    "error_message": "Invalid JSON format",
                    "error_code": "INVALID_JSON",
                },
            )
            await connection.send_message(error_message.model_dump(mode="json"))
            return False
        except Exception as e:
            logger.error(
                f"Error handling message from connection {connection_id}: {str(e)}"
            )
            return False

    def get_connection_count(self, session_id: Optional[str] = None) -> int:
        """
        Get the number of active connections.

        Args:
            session_id: Optional session ID to filter by

        Returns:
            int: Number of active connections
        """
        if session_id:
            return len(self._session_connections.get(session_id, set()))
        return len(self._connections)

    def get_session_connections(self, session_id: str) -> list[str]:
        """
        Get all connection IDs for a session.

        Args:
            session_id: Session ID to get connections for

        Returns:
            list[str]: list of connection IDs
        """
        return list(self._session_connections.get(session_id, set()))

    def get_connection_info(self, connection_id: str) -> Optional[dict[str, Any]]:
        """
        Get information about a specific connection.

        Args:
            connection_id: Connection ID to get info for

        Returns:
            Optional[dict[str, Any]]: Connection information or None if not found
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return None

        return {
            "connection_id": connection.connection_id,
            "session_id": connection.session_id,
            "client_info": connection.client_info,
            "connected_at": connection.connected_at.isoformat(),
            "last_ping": connection.last_ping.isoformat(),
            "is_active": connection.is_active,
        }

    async def disconnect_session(
        self, session_id: str, reason: str = "Session ended"
    ) -> int:
        """
        Disconnect all connections for a session.

        Args:
            session_id: Session ID to disconnect
            reason: Disconnect reason

        Returns:
            int: Number of connections disconnected
        """

        connection_ids = self._session_connections.get(session_id, set()).copy()

        if not connection_ids:
            return 0

        disconnect_count = 0
        for connection_id in connection_ids:
            if await self.disconnect(connection_id, code=1000, reason=reason):
                disconnect_count += 1

        logger.info(
            f"Disconnected {disconnect_count} connections for session {session_id}"
        )
        return disconnect_count

    async def cleanup(self) -> None:
        """Clean up all connections and stop background tasks."""

        logger.info("Cleaning up WebSocketManager")

        # Stop cleanup task
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Disconnect all connections
        connection_ids = list(self._connections.keys())
        for connection_id in connection_ids:
            await self.disconnect(connection_id, code=1001, reason="Server shutdown")

        logger.info("WebSocketManager cleanup completed")

    async def _send_to_connection(
        self, connection: WebSocketConnection, message: dict[str, Any]
    ) -> bool:
        """
        Send a message to a specific connection.

        Args:
            connection: WebSocket connection
            message: Message to send

        Returns:
            bool: True if successful, False otherwise
        """

        return await connection.send_message(message)

    async def _cleanup_failed_connections(self, connection_ids: list[str]) -> None:
        """
        Clean up failed connections.

        Args:
            connection_ids: list of connection IDs to clean up
        """

        for connection_id in connection_ids:
            await self.disconnect(connection_id, code=1011, reason="Connection failed")

    def _start_cleanup_task(self) -> None:
        """Start the background cleanup task."""
        try:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        except RuntimeError:
            # No event loop running, task will be created when first connection is made
            pass

    async def _cleanup_loop(self) -> None:
        """Background task to clean up stale connections."""
        while True:
            try:
                await asyncio.sleep(self._ping_interval)
                await self._cleanup_stale_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {str(e)}")

    async def _cleanup_stale_connections(self) -> None:
        """Clean up connections that haven't pinged recently."""
        current_time = datetime.now(timezone.utc)
        stale_connections = []

        for connection_id, connection in self._connections.items():
            time_since_ping = (current_time - connection.last_ping).total_seconds()
            if time_since_ping > self._connection_timeout:
                stale_connections.append(connection_id)

        if stale_connections:
            logger.info(f"Cleaning up {len(stale_connections)} stale connections")
            for connection_id in stale_connections:
                await self.disconnect(
                    connection_id, code=1000, reason="Connection timeout"
                )


# Global WebSocket manager instance
websocket_manager = WebSocketManager()
