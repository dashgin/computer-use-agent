"""
Chat interaction REST API endpoints.

This module implements message-related REST endpoints including:
- Sending messages to sessions
- Retrieving chat history with pagination
- Tool execution management
- Enhanced message features
"""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import MessageManagerDep, SessionManagerDep
from app.core.logging import get_logger
from app.core.message_manager import (
    MessageNotFoundError,
    MessageStorageError,
)
from app.core.session_manager import (
    SessionNotFoundError,
    SessionStateError,
)
from app.models.schemas import (
    ExecutionStatus,
    Message,
    MessageListResponse,
    MessageRole,
    PaginationParams,
    SendMessageRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["messages"])


@router.post(
    "/{session_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send message to session",
    description="Send a message to an active session for processing by the computer use agent",
)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    session_manager: SessionManagerDep,
) -> dict:
    """
    Send a message to a session.

    Args:
        session_id: The session ID to send the message to
        request: Message content request
        session_manager: Session manager dependency

    Returns:
        dict: Acknowledgment response

    Raises:
        HTTPException: If session not found, inactive, or message sending fails
    """
    try:
        logger.info(
            f"Sending message to session {session_id}: {request.content[:100]}..."
        )

        # Send message through session manager
        # Note: This will be enhanced when agent manager integration is complete
        await session_manager.send_message(
            session_id=session_id, message=request.content
        )

        logger.info(f"Message queued for processing in session: {session_id}")

        return {
            "message": "Message received and queued for processing",
            "session_id": session_id,
            "status": "accepted",
        }

    except SessionNotFoundError:
        logger.warning(f"Session not found for message: {session_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    except SessionStateError as e:
        logger.warning(f"Invalid session state for message: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        logger.error(f"Message validation error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to send message to session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message",
        )


@router.get(
    "/{session_id}/messages",
    response_model=MessageListResponse,
    summary="Get chat history",
    description="Retrieve chat history for a session with pagination",
)
async def get_chat_history(
    session_id: str,
    session_manager: SessionManagerDep,
    page_size: int = 50,
    page: int = 1,
) -> MessageListResponse:
    """
    Get chat history for a session.

    Args:
        session_id: The session ID to get history for
        page: Page number (1-based)
        page_size: Number of messages per page
        session_manager: Session manager dependency

    Returns:
        MessageListResponse: Paginated list of messages

    Raises:
        HTTPException: If session not found or history retrieval fails
    """
    try:
        logger.debug(
            f"Getting chat history for session {session_id} - page: {page}, size: {page_size}"
        )

        # Use enhanced pagination through MessageManager
        pagination_params = PaginationParams(page=page, page_size=page_size)
        response = await session_manager.get_chat_history(
            session_id=session_id, pagination=pagination_params
        )

        logger.debug(
            f"Retrieved {len(response.messages)} messages for session {session_id}"
        )
        return response

    except SessionNotFoundError:
        logger.warning(f"Session not found for chat history: {session_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    except ValueError as e:
        logger.error(f"Chat history validation error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get chat history for session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history",
        )


@router.get(
    "/{session_id}/messages/latest",
    response_model=list[Message],
    summary="Get latest messages",
    description="Get the most recent messages from a session",
)
async def get_latest_messages(
    session_id: str,
    session_manager: SessionManagerDep,
    limit: int = 10,
) -> list[Message]:
    """
    Get the latest messages from a session.

    Args:
        session_id: The session ID to get messages from
        limit: Number of latest messages to retrieve
        session_manager: Session manager dependency

    Returns:
        list[Message]: list of latest messages

    Raises:
        HTTPException: If session not found or message retrieval fails
    """
    try:
        logger.debug(f"Getting latest {limit} messages for session: {session_id}")

        # Use the enhanced pagination system
        pagination_params = PaginationParams(page=1, page_size=limit)
        response = await session_manager.get_chat_history(
            session_id=session_id, pagination=pagination_params
        )

        logger.debug(
            f"Retrieved {len(response.messages)} latest messages for session {session_id}"
        )
        return response.messages

    except SessionNotFoundError as e:
        logger.warning(f"Session not found for latest messages: {session_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        ) from e
    except Exception as e:
        logger.error(
            f"Failed to get latest messages for session {session_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve latest messages",
        ) from e


@router.get(
    "/{session_id}/messages/count",
    response_model=dict,
    summary="Get message count",
    description="Get the total number of messages in a session by role",
)
async def get_message_count(
    session_id: str, message_manager: MessageManagerDep
) -> dict:
    """
    Get the total message count for a session by role.

    Args:
        session_id: The session ID to count messages for
        message_manager: Message manager dependency

    Returns:
        dict: Message count information by role

    Raises:
        HTTPException: If session not found or count retrieval fails
    """
    try:
        logger.debug(f"Getting message count for session: {session_id}")

        # Use MessageManager for efficient role-based counting
        role_counts = await message_manager.get_message_count_by_role(session_id)
        total_messages = sum(role_counts.values())

        response = {
            "session_id": session_id,
            "total_messages": total_messages,
            "by_role": role_counts,
        }

        logger.debug(f"Message count for session {session_id}: {total_messages} total")
        return response

    except MessageStorageError as e:
        logger.error(f"Message storage error for session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get message count",
        )
    except Exception as e:
        logger.error(f"Failed to get message count for session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get message count",
        )


@router.get(
    "/{session_id}/messages/filtered",
    response_model=MessageListResponse,
    summary="Get filtered messages",
    description="Retrieve messages filtered by role with pagination",
)
async def get_filtered_messages(
    session_id: str,
    session_manager: SessionManagerDep,
    page: int = 1,
    page_size: int = 50,
    role: MessageRole | None = None,
) -> MessageListResponse:
    """
    Get messages filtered by role for a session.

    Args:
        session_id: The session ID to get messages for
        role: Message role to filter by
        page: Page number (1-based)
        page_size: Number of messages per page
        session_manager: Session manager dependency

    Returns:
        MessageListResponse: Paginated list of filtered messages

    Raises:
        HTTPException: If session not found or retrieval fails
    """
    try:
        logger.debug(
            f"Getting {role.value} messages for session {session_id} - page: {page}, size: {page_size}"
        )

        pagination_params = PaginationParams(page=page, page_size=page_size)
        response = await session_manager.get_chat_history(
            session_id=session_id, pagination=pagination_params, role_filter=role
        )

        logger.debug(
            f"Retrieved {len(response.messages)} {role.value} messages for session {session_id}"
        )
        return response

    except SessionNotFoundError as e:
        logger.warning(f"Session not found for filtered messages: {session_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        ) from e
    except MessageStorageError as e:
        logger.error(f"Message retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve filtered messages",
        ) from e
    except Exception as e:
        logger.error(
            f"Failed to get filtered messages for session {session_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve filtered messages",
        ) from e


@router.get(
    "/{session_id}/messages/{message_id}",
    response_model=Message,
    summary="Get specific message",
    description="Retrieve a specific message by ID",
)
async def get_message_by_id(
    session_id: str,
    message_id: int,
    message_manager: MessageManagerDep,
) -> Message:
    """
    Get a specific message by ID.

    Args:
        session_id: The session ID (for validation)
        message_id: The message ID to retrieve
        message_manager: Message manager dependency

    Returns:
        Message: The requested message

    Raises:
        HTTPException: If message not found or retrieval fails
    """
    try:
        logger.debug(f"Getting message {message_id} for session {session_id}")

        message = await message_manager.get_message_by_id(message_id)

        # Validate that the message belongs to the specified session
        if message.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Message {message_id} not found in session {session_id}",
            )

        logger.debug(f"Retrieved message {message_id} for session {session_id}")
        return message

    except MessageNotFoundError as e:
        logger.warning(f"Message {message_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        ) from e
    except MessageStorageError as e:
        logger.error(f"Message storage error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve message",
        ) from e
    except Exception as e:
        logger.error(f"Failed to get message {message_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve message",
        ) from e


@router.get(
    "/{session_id}/tool-executions",
    response_model=dict,
    summary="Get tool executions",
    description="Retrieve tool executions for a session with pagination and filtering",
)
async def get_tool_executions(
    session_id: str,
    message_manager: MessageManagerDep,
    page: int = 1,
    page_size: int = 20,
    status_filter: ExecutionStatus | None = None,
) -> dict:
    """
    Get tool executions for a session.

    Args:
        session_id: The session ID to get executions for
        page: Page number (1-based)
        page_size: Number of executions per page
        status_filter: Optional status filter

    Returns:
        dict: Paginated list of tool executions

    Raises:
        HTTPException: If session not found or retrieval fails
    """
    try:
        logger.debug(
            f"Getting tool executions for session {session_id} - page: {page}, size: {page_size}"
        )

        pagination_params = PaginationParams(page=page, page_size=page_size)
        executions, total = await message_manager.get_tool_executions_for_session(
            session_id=session_id,
            status_filter=status_filter,
            pagination=pagination_params,
        )

        # Calculate pagination info
        has_next = (page * page_size) < total

        response = {
            "tool_executions": [execution.model_dump() for execution in executions],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": has_next,
            "status_filter": status_filter.value if status_filter else None,
        }

        logger.debug(
            f"Retrieved {len(executions)} tool executions for session {session_id}"
        )
        return response

    except MessageStorageError as e:
        logger.error(f"Tool execution retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tool executions",
        ) from e
    except Exception as e:
        logger.error(
            f"Failed to get tool executions for session {session_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tool executions",
        ) from e
