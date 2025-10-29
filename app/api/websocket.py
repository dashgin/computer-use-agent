"""
WebSocket API endpoints and handlers.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.core.agent_manager import AgentManager
from app.core.config import settings
from app.core.logging import get_logger
from app.core.session_manager import SessionManager, SessionNotFoundError
from app.core.websocket_manager import websocket_manager

logger = get_logger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time session communication.

    This endpoint provides:
    - Session validation and authentication
    - Real-time message processing through agent manager
    - Progress updates streaming
    - Error handling and recovery

    Args:
        websocket: WebSocket connection
        session_id: Session ID to connect to
    """
    connection_id = None
    try:
        session_manager = SessionManager()

        # Validate session exists and is active
        try:
            session = await session_manager.get_session(session_id)
            if session.status.value not in ["active"]:
                await websocket.close(
                    code=4003,
                    reason=f"Session {session_id} is not active (status: {session.status.value})",
                )
                return
        except SessionNotFoundError:
            await websocket.close(code=4004, reason=f"Session {session_id} not found")
            return

        # Optional: Check authentication if API key is provided
        api_key = websocket.headers.get("x-api-key")
        if settings.REQUIRE_API_KEY and not api_key:
            await websocket.close(code=4001, reason="API key required")
            return

        # Extract client info from headers
        client_info = {
            "user_agent": websocket.headers.get("user-agent", "unknown"),
            "origin": websocket.headers.get("origin", "unknown"),
            "api_key_provided": bool(api_key),
        }

        # Connect to WebSocket manager
        connection_id = await websocket_manager.connect(
            websocket=websocket, session_id=session_id, client_info=client_info
        )

        logger.info(f"WebSocket connection established for session {session_id}")

        # Initialize agent manager if we have an API key
        agent_manager = None
        if api_key or hasattr(settings, "ANTHROPIC_API_KEY"):
            try:
                agent_manager = AgentManager(
                    api_key=api_key or settings.ANTHROPIC_API_KEY,
                    model=getattr(
                        settings, "DEFAULT_MODEL"
                    ),
                )
                logger.info(f"Agent manager initialized for session {session_id}")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize agent manager for session {session_id}: {e}"
                )
                await websocket_manager.send_to_session(
                    session_id=session_id,
                    message_type="error",
                    content="Agent not available - messages will be echoed only",
                    error_code="AGENT_INIT_FAILED",
                )

        # Send connection success message
        await websocket_manager.send_to_session(
            session_id=session_id,
            message_type="system",
            content=f"Connected to session {session_id}. Real-time updates enabled.",
            role="system",
        )

        # Handle incoming messages
        while True:
            try:
                # Receive message from client
                message = await websocket.receive_text()

                # Handle the message through WebSocket message handler
                await websocket_manager.handle_client_message(
                    connection_id=connection_id,
                    message=message,
                    message_handler=lambda sid, data, cid: handle_websocket_message(
                        sid, data, cid, session_manager, agent_manager
                    ),
                )

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for session {session_id}")
                break
            except Exception as e:
                logger.error(
                    f"Error handling WebSocket message for session {session_id}: {e}"
                )
                # Send error to client and continue
                await websocket_manager.send_to_session(
                    session_id=session_id,
                    message_type="error",
                    content="Message processing error",
                    error_code="WEBSOCKET_ERROR",
                    error_details=str(e),
                )

    except Exception as e:
        logger.error(f"WebSocket connection error for session {session_id}: {e}")
        if connection_id:
            await websocket_manager.send_to_session(
                session_id=session_id,
                message_type="error",
                content="Connection error occurred",
                error_code="CONNECTION_ERROR",
            )
        raise HTTPException(
            status_code=500, detail="WebSocket connection failed"
        ) from e
    finally:
        # Clean up connection
        if connection_id:
            await websocket_manager.disconnect(connection_id)


async def handle_websocket_message(
    session_id: str,
    message_data: dict,
    connection_id: str,
    session_manager: SessionManager,
    agent_manager: Optional[AgentManager] = None,
):
    """
    Handle WebSocket messages with simplified integration.

    Args:
        session_id: Session ID that sent the message
        message_data: Parsed message data
        connection_id: Connection ID that sent the message
        session_manager: Session manager instance
        agent_manager: Optional agent manager instance
    """
    message_type = message_data.get("type", "unknown")

    logger.debug(
        f"Handling WebSocket message type '{message_type}' for session {session_id}"
    )

    try:
        # Handle different message types
        if message_type == "chat_message":
            content = message_data.get("content", "").strip()
            if not content:
                await websocket_manager.send_to_session(
                    session_id=session_id,
                    message_type="error",
                    content="Message content cannot be empty",
                )
                return

            # Save user message to database
            from app.core.message_manager import message_manager

            try:
                # Save the user message
                await message_manager.store_user_message(
                    session_id=session_id,
                    content=content,
                )

                # Echo user message back via websocket
                await websocket_manager.send_to_session(
                    session_id=session_id,
                    message_type="user_message",
                    content=content,
                    role="user",
                )

                # Send processing started message
                await websocket_manager.send_to_session(
                    session_id=session_id,
                    message_type="processing",
                    content="Processing message...",
                )

                if agent_manager:
                    # Process message through agent with real-time streaming
                    try:
                        # Create progress callback for real-time updates
                        async def progress_callback(update):
                            # Send the update via websocket
                            await websocket_manager.send_to_session(
                                session_id=session_id,
                                message_type=update.get("type", "agent_response"),
                                content=update.get("content", ""),
                                role=update.get("role", "assistant"),
                                **{
                                    k: v
                                    for k, v in update.items()
                                    if k not in ["type", "content", "role"]
                                },
                            )

                        # Process message with streaming callback
                        await agent_manager.process_message_simple(
                            session_id=session_id,
                            message=content,
                            progress_callback=progress_callback,
                        )

                    except Exception as e:
                        logger.error(f"Agent processing error: {e}")
                        await websocket_manager.send_to_session(
                            session_id=session_id,
                            message_type="error",
                            content=f"Agent processing error: {str(e)}",
                        )
                else:
                    # Fallback: echo message without agent processing
                    response = f"Echo: {content} (Agent not available)"

                    # Save echo response
                    await message_manager.store_assistant_message(
                        session_id=session_id,
                        content=response,
                    )

                    await websocket_manager.send_to_session(
                        session_id=session_id,
                        message_type="agent_response",
                        content=response,
                        role="assistant",
                    )

            except Exception as e:
                logger.error(f"Database error: {e}")
                await websocket_manager.send_to_session(
                    session_id=session_id,
                    message_type="error",
                    content=f"Database error: {str(e)}",
                )

        elif message_type == "get_status":
            # Handle status requests
            session = await session_manager.get_session(session_id)
            await websocket_manager.send_to_session(
                session_id=session_id,
                message_type="status_response",
                content="Session status",
                status=session.status.value,
                title=session.title,
                created_at=session.created_at.isoformat(),
                connection_count=websocket_manager.get_connection_count(session_id),
            )

        elif message_type == "get_history":
            # Handle history requests
            limit = message_data.get("limit", 10)
            try:
                response = await session_manager.get_chat_history(
                    session_id, limit=limit
                )
                await websocket_manager.send_to_session(
                    session_id=session_id,
                    message_type="history_response",
                    content="Chat history",
                    messages=[msg.model_dump(mode="json") for msg in response.messages],
                    total_count=response.total,
                )
            except Exception as e:
                await websocket_manager.send_to_session(
                    session_id=session_id,
                    message_type="error",
                    content=f"Failed to retrieve history: {str(e)}",
                    error_code="HISTORY_ERROR",
                )

        elif message_type == "ping":
            # Ping is already handled by the WebSocket manager
            pass

        else:
            logger.warning(
                f"Unknown message type '{message_type}' from session {session_id}"
            )
            await websocket_manager.send_to_session(
                session_id=session_id,
                message_type="error",
                content=f"Unknown message type: {message_type}",
                error_code="UNKNOWN_MESSAGE_TYPE",
            )

    except Exception as e:
        logger.error(
            f"Error processing WebSocket message for session {session_id}: {e}"
        )
        await websocket_manager.send_to_session(
            session_id=session_id,
            message_type="error",
            content="Failed to process message",
            error_code="MESSAGE_PROCESSING_ERROR",
            error_details=str(e),
        )


@router.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection statistics."""
    return {
        "total_connections": websocket_manager.get_connection_count(),
        "active_sessions": len(websocket_manager._session_connections),
    } 