"""
Message management core functionality.

This module implements the MessageManager class that provides comprehensive
message persistence, chat history retrieval, and tool execution tracking
with proper transaction management and data consistency.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import asc, delete, desc, func, select
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.db.connection import get_db_session
from app.models.database import (
    Message as MessageModel,
    ToolExecution as ToolExecutionModel,
)
from app.models.schemas import (
    ContentType,
    ExecutionStatus,
    Message,
    MessageListResponse,
    MessageRole,
    PaginationParams,
    ToolExecution,
)

logger = get_logger(__name__)


class MessageNotFoundError(Exception):
    """Raised when a message is not found."""


class MessageStorageError(Exception):
    """Raised when message storage operations fail."""


class MessageManager:
    """
    Manages message persistence and chat history with comprehensive features.

    This class provides:
    - Message storage with proper role and content type handling
    - Tool execution tracking and result persistence
    - Efficient chat history retrieval with pagination
    - Data consistency and transaction management
    - Message metadata handling and search capabilities
    """

    def __init__(self):
        """Initialize the MessageManager."""
        logger.info("MessageManager initialized")

    async def store_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        content_type: ContentType = ContentType.TEXT,
        tool_use_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Message:
        """
        Store a message in the database.

        Args:
            session_id: Session ID for the message
            role: Message role (user, assistant, tool)
            content: Message content
            content_type: Type of content (text, tool_use, tool_result)
            tool_use_id: Optional tool use ID for tool-related messages
            metadata: Optional message metadata

        Returns:
            Message: The stored message object

        Raises:
            MessageStorageError: If storage fails
        """
        logger.debug(f"Storing {role.value} message for session {session_id}")

        async for db_session in get_db_session():
            try:
                message_model = MessageModel(
                    session_id=session_id,
                    role=role.value,
                    content=content.strip() if role == MessageRole.USER else content,
                    content_type=content_type.value,
                    tool_use_id=tool_use_id,
                    message_metadata=metadata or {},
                )

                db_session.add(message_model)
                await db_session.commit()
                await db_session.refresh(message_model)

                message = Message.model_validate(message_model)
                logger.debug(f"Stored message {message.id} for session {session_id}")
                return message

            except Exception as e:
                await db_session.rollback()
                logger.error(
                    f"Failed to store {role.value} message for session {session_id}: {e}"
                )
                raise MessageStorageError(
                    f"Failed to store {role.value} message: {e}"
                ) from e

    async def store_user_message(
        self, session_id: str, content: str, metadata: Optional[dict[str, Any]] = None
    ) -> Message:
        """
        Store a user message in the database.

        Args:
            session_id: Session ID for the message
            content: Message content
            metadata: Optional message metadata

        Returns:
            Message: The stored message object

        Raises:
            MessageStorageError: If storage fails
        """
        return await self.store_message(
            session_id=session_id,
            role=MessageRole.USER,
            content=content,
            content_type=ContentType.TEXT,
            metadata=metadata,
        )

    async def store_assistant_message(
        self,
        session_id: str,
        content: str,
        content_type: ContentType = ContentType.TEXT,
        tool_use_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Message:
        """
        Store an assistant message in the database.

        Args:
            session_id: Session ID for the message
            content: Message content
            content_type: Type of content (text, tool_use, tool_result)
            tool_use_id: Optional tool use ID for tool-related messages
            metadata: Optional message metadata

        Returns:
            Message: The stored message object

        Raises:
            MessageStorageError: If storage fails
        """
        return await self.store_message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=content,
            content_type=content_type,
            tool_use_id=tool_use_id,
            metadata=metadata,
        )

    async def store_tool_message(
        self,
        session_id: str,
        tool_result: str,
        tool_use_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Message:
        """
        Store a tool result message in the database.

        Args:
            session_id: Session ID for the message
            tool_result: Tool execution result content
            tool_use_id: Tool use ID for association
            metadata: Optional message metadata

        Returns:
            Message: The stored message object

        Raises:
            MessageStorageError: If storage fails
        """
        return await self.store_message(
            session_id=session_id,
            role=MessageRole.TOOL,
            content=tool_result,
            content_type=ContentType.TOOL_RESULT,
            tool_use_id=tool_use_id,
            metadata=metadata,
        )

    async def get_chat_history(
        self,
        session_id: str,
        pagination: Optional[PaginationParams] = None,
        role_filter: Optional[MessageRole] = None,
        include_tool_executions: bool = False,
    ) -> MessageListResponse:
        """
        Retrieve chat history for a session with pagination and filtering.

        Args:
            session_id: Session ID to get history for
            pagination: Pagination parameters
            role_filter: Optional role filter
            include_tool_executions: Whether to include tool execution details

        Returns:
            MessageListResponse: Paginated list of messages

        Raises:
            MessageStorageError: If retrieval fails
        """
        if pagination is None:
            pagination = PaginationParams(page=1, page_size=50)

        logger.debug(f"Retrieving chat history for session {session_id}")

        async for db_session in get_db_session():
            try:
                # Build base query
                query = select(MessageModel).where(
                    MessageModel.session_id == session_id
                )

                # Apply role filter if specified
                if role_filter:
                    query = query.where(MessageModel.role == role_filter.value)

                # Include tool executions if requested
                if include_tool_executions:
                    query = query.options(selectinload(MessageModel.tool_executions))

                # Get total count for pagination
                count_query = select(func.count(MessageModel.id)).where(
                    MessageModel.session_id == session_id
                )
                if role_filter:
                    count_query = count_query.where(
                        MessageModel.role == role_filter.value
                    )

                total_result = await db_session.execute(count_query)
                total = total_result.scalar()

                # Apply pagination and ordering
                offset = (pagination.page - 1) * pagination.page_size
                query = (
                    query.order_by(asc(MessageModel.timestamp))  # Chronological order
                    .offset(offset)
                    .limit(pagination.page_size)
                )

                # Execute query
                result = await db_session.execute(query)
                message_models = result.scalars().all()

                # Convert to Pydantic models
                messages = [Message.model_validate(model) for model in message_models]

                # Calculate pagination info
                has_next = offset + len(messages) < total

                response = MessageListResponse(
                    messages=messages,
                    total=total,
                    page=pagination.page,
                    page_size=pagination.page_size,
                    has_next=has_next,
                )

                logger.debug(
                    f"Retrieved {len(messages)} messages for session {session_id}"
                )
                return response

            except Exception as e:
                logger.error(
                    f"Failed to retrieve chat history for session {session_id}: {e}"
                )
                raise MessageStorageError(
                    f"Failed to retrieve chat history: {e}"
                ) from e

    async def get_message_by_id(self, message_id: int) -> Message:
        """
        Retrieve a specific message by ID.

        Args:
            message_id: Message ID to retrieve

        Returns:
            Message: The message object

        Raises:
            MessageNotFoundError: If message not found
            MessageStorageError: If retrieval fails
        """
        logger.debug(f"Retrieving message {message_id}")

        async for db_session in get_db_session():
            try:
                query = select(MessageModel).where(MessageModel.id == message_id)
                result = await db_session.execute(query)
                message_model = result.scalar_one_or_none()

                if not message_model:
                    raise MessageNotFoundError(f"Message {message_id} not found")

                message = Message.model_validate(message_model)
                logger.debug(f"Retrieved message {message_id}")
                return message

            except MessageNotFoundError:
                raise
            except Exception as e:
                logger.error(f"Failed to retrieve message {message_id}: {e}")
                raise MessageStorageError(f"Failed to retrieve message: {e}") from e

    async def store_tool_execution(
        self,
        session_id: str,
        message_id: int,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_output: Optional[dict[str, Any]] = None,
        status: ExecutionStatus = ExecutionStatus.PENDING,
        error_message: Optional[str] = None,
    ) -> ToolExecution:
        """
        Store a tool execution record.

        Args:
            session_id: Session ID
            message_id: Associated message ID
            tool_name: Name of the executed tool
            tool_input: Tool input parameters
            tool_output: Tool output results
            status: Execution status
            error_message: Error message if failed

        Returns:
            ToolExecution: The stored tool execution object

        Raises:
            MessageStorageError: If storage fails
        """
        execution_id = str(uuid.uuid4())
        logger.debug(f"Storing tool execution {execution_id} for session {session_id}")

        async for db_session in get_db_session():
            try:
                now = datetime.now(timezone.utc)

                tool_execution_model = ToolExecutionModel(
                    id=execution_id,
                    session_id=session_id,
                    message_id=message_id,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_output=tool_output,
                    status=status.value,
                    started_at=now,
                    completed_at=now
                    if status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED]
                    else None,
                    error_message=error_message,
                )

                db_session.add(tool_execution_model)
                await db_session.commit()
                await db_session.refresh(tool_execution_model)

                tool_execution = ToolExecution.model_validate(tool_execution_model)
                logger.debug(
                    f"Stored tool execution {execution_id} for session {session_id}"
                )
                return tool_execution

            except Exception as e:
                await db_session.rollback()
                logger.error(
                    f"Failed to store tool execution for session {session_id}: {e}"
                )
                raise MessageStorageError(f"Failed to store tool execution: {e}") from e

    async def update_tool_execution(
        self,
        execution_id: str,
        tool_output: Optional[dict[str, Any]] = None,
        status: Optional[ExecutionStatus] = None,
        error_message: Optional[str] = None,
    ) -> ToolExecution:
        """
        Update a tool execution record.

        Args:
            execution_id: Tool execution ID to update
            tool_output: Updated tool output
            status: Updated execution status
            error_message: Updated error message

        Returns:
            ToolExecution: The updated tool execution object

        Raises:
            MessageNotFoundError: If tool execution not found
            MessageStorageError: If update fails
        """
        logger.debug(f"Updating tool execution {execution_id}")

        async for db_session in get_db_session():
            try:
                # Get the existing tool execution
                query = select(ToolExecutionModel).where(
                    ToolExecutionModel.id == execution_id
                )
                result = await db_session.execute(query)
                tool_execution_model = result.scalar_one_or_none()

                if not tool_execution_model:
                    raise MessageNotFoundError(
                        f"Tool execution {execution_id} not found"
                    )

                # Update fields
                if tool_output is not None:
                    tool_execution_model.tool_output = tool_output

                if status is not None:
                    tool_execution_model.status = status.value
                    if status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED]:
                        tool_execution_model.completed_at = datetime.now()

                if error_message is not None:
                    tool_execution_model.error_message = error_message

                await db_session.commit()
                await db_session.refresh(tool_execution_model)

                tool_execution = ToolExecution.model_validate(tool_execution_model)
                logger.debug(f"Updated tool execution {execution_id}")
                return tool_execution

            except MessageNotFoundError:
                raise
            except Exception as e:
                await db_session.rollback()
                logger.error(f"Failed to update tool execution {execution_id}: {e}")
                raise MessageStorageError(
                    f"Failed to update tool execution: {e}"
                ) from e

    async def get_tool_executions_for_session(
        self,
        session_id: str,
        status_filter: Optional[ExecutionStatus] = None,
        pagination: Optional[PaginationParams] = None,
    ) -> tuple[list[ToolExecution], int]:
        """
        Get tool executions for a session with optional filtering.

        Args:
            session_id: Session ID to get executions for
            status_filter: Optional status filter
            pagination: Optional pagination parameters

        Returns:
            tuple[list[ToolExecution], int]: List of tool executions and total count

        Raises:
            MessageStorageError: If retrieval fails
        """
        if pagination is None:
            pagination = PaginationParams(page=1, page_size=50)

        logger.debug(f"Retrieving tool executions for session {session_id}")

        async for db_session in get_db_session():
            try:
                # Build base query
                query = select(ToolExecutionModel).where(
                    ToolExecutionModel.session_id == session_id
                )

                # Apply status filter if specified
                if status_filter:
                    query = query.where(
                        ToolExecutionModel.status == status_filter.value
                    )

                # Get total count
                count_query = select(func.count(ToolExecutionModel.id)).where(
                    ToolExecutionModel.session_id == session_id
                )
                if status_filter:
                    count_query = count_query.where(
                        ToolExecutionModel.status == status_filter.value
                    )

                total_result = await db_session.execute(count_query)
                total = total_result.scalar()

                # Apply pagination and ordering
                offset = (pagination.page - 1) * pagination.page_size
                query = (
                    query.order_by(desc(ToolExecutionModel.started_at))
                    .offset(offset)
                    .limit(pagination.page_size)
                )

                # Execute query
                result = await db_session.execute(query)
                execution_models = result.scalars().all()

                # Convert to Pydantic models
                executions = [
                    ToolExecution.model_validate(model) for model in execution_models
                ]

                logger.debug(
                    f"Retrieved {len(executions)} tool executions for session {session_id}"
                )
                return executions, total

            except Exception as e:
                logger.error(
                    f"Failed to retrieve tool executions for session {session_id}: {e}"
                )
                raise MessageStorageError(
                    f"Failed to retrieve tool executions: {e}"
                ) from e

    async def delete_messages_for_session(self, session_id: str) -> int:
        """
        Delete all messages for a session.

        Args:
            session_id: Session ID to delete messages for

        Returns:
            int: Number of messages deleted

        Raises:
            MessageStorageError: If deletion fails
        """
        logger.info(f"Deleting all messages for session {session_id}")

        async for db_session in get_db_session():
            try:
                # Get count before deletion
                count_query = select(func.count(MessageModel.id)).where(
                    MessageModel.session_id == session_id
                )
                count_result = await db_session.execute(count_query)
                count = count_result.scalar()

                # Delete messages (tool executions will be deleted by CASCADE)
                delete_query = delete(MessageModel).where(
                    MessageModel.session_id == session_id
                )
                await db_session.execute(delete_query)
                await db_session.commit()

                logger.info(f"Deleted {count} messages for session {session_id}")
                return count

            except Exception as e:
                await db_session.rollback()
                logger.error(f"Failed to delete messages for session {session_id}: {e}")
                raise MessageStorageError(f"Failed to delete messages: {e}") from e

    async def get_message_count_by_role(self, session_id: str) -> dict[str, int]:
        """
        Get message count by role for a session.

        Args:
            session_id: Session ID to count messages for

        Returns:
            dict[str, int]: Count of messages by role

        Raises:
            MessageStorageError: If count retrieval fails
        """
        logger.debug(f"Getting message count by role for session {session_id}")

        async for db_session in get_db_session():
            try:
                query = (
                    select(MessageModel.role, func.count(MessageModel.id))
                    .where(MessageModel.session_id == session_id)
                    .group_by(MessageModel.role)
                )

                result = await db_session.execute(query)
                role_counts = dict(result.fetchall())

                # Ensure all roles are represented
                for role in MessageRole:
                    if role.value not in role_counts:
                        role_counts[role.value] = 0

                logger.debug(
                    f"Message count by role for session {session_id}: {role_counts}"
                )
                return role_counts

            except Exception as e:
                logger.error(
                    f"Failed to get message count for session {session_id}: {e}"
                )
                raise MessageStorageError(f"Failed to get message count: {e}") from e


# Global message manager instance
message_manager = MessageManager()
