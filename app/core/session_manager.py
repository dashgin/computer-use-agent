"""
Session management core functionality.

This module implements the SessionManager class that provides CRUD operations
for sessions, lifecycle management, and state tracking with database persistence.
"""

import uuid
from typing import Any, Optional

from sqlalchemy import asc, desc, func, select, update
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.db.connection import get_db_session
from app.models.database import Session as SessionModel
from app.models.schemas import (
    Message,
    MessageListResponse,
    MessageRole,
    PaginationParams,
    Session,
    SessionListResponse,
    SessionStatus,
    SortParams,
)

logger = get_logger(__name__)


class SessionNotFoundError(Exception):
    """Raised when a session is not found."""


class SessionStateError(Exception):
    """Raised when an invalid session state transition is attempted."""


class SessionManager:
    """
    Manages computer use agent sessions with CRUD operations and lifecycle management.

    This class provides comprehensive session management including:
    - Session creation, retrieval, updating, and deletion
    - Session state tracking and validation
    - Database persistence with transaction management
    - Session listing with pagination and sorting
    """

    def __init__(self):
        """Initialize the SessionManager."""
        logger.info("SessionManager initialized")
        self._valid_status_transitions = {
            SessionStatus.ACTIVE: [
                SessionStatus.COMPLETED,
                SessionStatus.FAILED,
                SessionStatus.TERMINATED,
            ],
            SessionStatus.COMPLETED: [SessionStatus.TERMINATED],
            SessionStatus.FAILED: [SessionStatus.TERMINATED],
            SessionStatus.TERMINATED: [],  # Terminal state
        }

    async def create_session(
        self,
        title: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """
        Create a new session with the provided parameters.

        Args:
            title: Optional session title
            metadata: Optional session metadata dictionary
            session_id: Optional custom session ID (generates UUID if not provided)

        Returns:
            Session: The created session object

        Raises:
            ValueError: If session_id is provided but already exists
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        if metadata is None:
            metadata = {}

        logger.info(f"Creating new session with ID: {session_id}")

        async for db_session in get_db_session():
            try:
                # Check if session_id already exists
                existing = await db_session.get(SessionModel, session_id)
                if existing:
                    raise ValueError(f"Session with ID {session_id} already exists")

                # Create new session model
                session_model = SessionModel(
                    id=session_id,
                    title=title,
                    session_metadata=metadata,
                    status=SessionStatus.ACTIVE.value,
                )

                db_session.add(session_model)
                await db_session.commit()
                await db_session.refresh(session_model)

                # Convert to Pydantic model
                session = Session.model_validate(session_model)

                logger.info(f"Successfully created session: {session_id}")
                return session

            except Exception as e:
                await db_session.rollback()
                logger.error(f"Failed to create session {session_id}: {str(e)}")
                raise

    async def get_session(self, session_id: str) -> Session:
        """
        Retrieve a session by its ID.

        Args:
            session_id: The session ID to retrieve

        Returns:
            Session: The session object

        Raises:
            SessionNotFoundError: If the session doesn't exist
        """
        logger.debug(f"Retrieving session: {session_id}")

        async for db_session in get_db_session():
            session_model = await db_session.get(SessionModel, session_id)

            if not session_model:
                logger.warning(f"Session not found: {session_id}")
                raise SessionNotFoundError(f"Session {session_id} not found")

            session = Session.model_validate(session_model)
            logger.debug(f"Successfully retrieved session: {session_id}")
            return session

    async def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Session:
        """
        Update an existing session with new values.

        Args:
            session_id: The session ID to update
            title: New title (if provided)
            status: New status (if provided)
            metadata: New metadata (if provided)

        Returns:
            Session: The updated session object

        Raises:
            SessionNotFoundError: If the session doesn't exist
            SessionStateError: If the status transition is invalid
        """
        logger.info(f"Updating session: {session_id}")

        async for db_session in get_db_session():
            try:
                # Get existing session
                session_model = await db_session.get(SessionModel, session_id)
                if not session_model:
                    raise SessionNotFoundError(f"Session {session_id} not found")

                # Validate status transition if status is being updated
                if status is not None:
                    current_status = SessionStatus(session_model.status)
                    if not self._is_valid_status_transition(current_status, status):
                        raise SessionStateError(
                            f"Invalid status transition from {current_status} to {status}"
                        )

                # Update fields - let database handle updated_at automatically
                update_data = {}

                if title is not None:
                    update_data["title"] = title
                if status is not None:
                    update_data["status"] = status.value
                if metadata is not None:
                    update_data["session_metadata"] = metadata

                # Perform update
                await db_session.execute(
                    update(SessionModel)
                    .where(SessionModel.id == session_id)
                    .values(**update_data)
                )

                await db_session.commit()

                # Refresh and return updated session
                await db_session.refresh(session_model)
                session = Session.model_validate(session_model)

                logger.info(f"Successfully updated session: {session_id}")
                return session

            except Exception as e:
                await db_session.rollback()
                logger.error(f"Failed to update session {session_id}: {str(e)}")
                raise

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all associated data.

        Args:
            session_id: The session ID to delete

        Returns:
            bool: True if session was deleted, False if it didn't exist
        """
        logger.info(f"Deleting session: {session_id}")

        async for db_session in get_db_session():
            try:
                # Check if session exists
                session_model = await db_session.get(SessionModel, session_id)
                if not session_model:
                    logger.warning(f"Session not found for deletion: {session_id}")
                    return False

                # Delete session (cascade will handle related records)
                await db_session.delete(session_model)
                await db_session.commit()

                logger.info(f"Successfully deleted session: {session_id}")
                return True

            except Exception as e:
                await db_session.rollback()
                logger.error(f"Failed to delete session {session_id}: {str(e)}")
                raise

    async def list_sessions(
        self,
        pagination: Optional[PaginationParams] = None,
        sort: Optional[SortParams] = None,
        status_filter: Optional[SessionStatus] = None,
    ) -> SessionListResponse:
        """
        list sessions with pagination, sorting, and filtering.

        Args:
            pagination: Pagination parameters
            sort: Sorting parameters
            status_filter: Optional status filter

        Returns:
            SessionListResponse: Paginated list of sessions
        """
        logger.debug(
            f"Listing sessions - page: {pagination.page}, size: {pagination.page_size}"
        )

        async for db_session in get_db_session():
            # Build base query
            query = select(SessionModel)

            # Apply status filter
            if status_filter:
                query = query.where(SessionModel.status == status_filter.value)

            # Apply sorting
            sort_column = getattr(SessionModel, sort.sort_by)
            if sort.sort_order == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(asc(sort_column))

            # Get total count
            count_query = select(func.count(SessionModel.id))
            if status_filter:
                count_query = count_query.where(
                    SessionModel.status == status_filter.value
                )

            total_result = await db_session.execute(count_query)
            total = total_result.scalar()

            # Apply pagination
            offset = (pagination.page - 1) * pagination.page_size
            query = query.offset(offset).limit(pagination.page_size)

            # Execute query
            result = await db_session.execute(query)
            session_models = result.scalars().all()

            # Convert to Pydantic models
            sessions = [Session.model_validate(model) for model in session_models]

            # Calculate pagination info
            has_next = offset + len(sessions) < total

            response = SessionListResponse(
                sessions=sessions,
                total=total,
                page=pagination.page,
                page_size=pagination.page_size,
                has_next=has_next,
            )

            logger.debug(f"Retrieved {len(sessions)} sessions (total: {total})")
            return response

    async def get_session_with_messages(self, session_id: str) -> tuple[Session, list]:
        """
        Retrieve a session along with its message history.

        Args:
            session_id: The session ID to retrieve

        Returns:
            tuple[Session, list]: Session object and list of messages

        Raises:
            SessionNotFoundError: If the session doesn't exist
        """
        logger.debug(f"Retrieving session with messages: {session_id}")

        async for db_session in get_db_session():
            # Query session with messages eagerly loaded
            query = (
                select(SessionModel)
                .options(selectinload(SessionModel.messages))
                .where(SessionModel.id == session_id)
            )

            result = await db_session.execute(query)
            session_model = result.scalar_one_or_none()

            if not session_model:
                raise SessionNotFoundError(f"Session {session_id} not found")

            # Convert to Pydantic models
            session = Session.model_validate(session_model)

            # Sort messages by timestamp
            messages = sorted(session_model.messages, key=lambda m: m.timestamp)

            logger.debug(
                f"Retrieved session {session_id} with {len(messages)} messages"
            )
            return session, messages

    async def update_session_status(
        self, session_id: str, status: SessionStatus
    ) -> Session:
        """
        Update only the status of a session.

        Args:
            session_id: The session ID to update
            status: New status

        Returns:
            Session: The updated session object

        Raises:
            SessionNotFoundError: If the session doesn't exist
            SessionStateError: If the status transition is invalid
        """
        return await self.update_session(session_id, status=status)

    async def session_exists(self, session_id: str) -> bool:
        """
        Check if a session exists.

        Args:
            session_id: The session ID to check

        Returns:
            bool: True if session exists, False otherwise
        """
        try:
            await self.get_session(session_id)
            return True
        except SessionNotFoundError:
            return False

    async def get_active_sessions(self) -> list[Session]:
        """
        Get all active sessions.

        Returns:
            list[Session]: list of active sessions
        """
        response = await self.list_sessions(
            pagination=PaginationParams(
                page=1, page_size=100
            ),  # Max page size for active sessions
            status_filter=SessionStatus.ACTIVE,
        )
        return response.sessions

    async def send_message(
        self,
        session_id: str,
        message: str,
        agent_manager=None,
        progress_callback=None,
        tool_callback=None,
        error_callback=None,
    ) -> Message:
        """
        Send a message to a session and process it through the agent.

        Args:
            session_id: The session ID to send message to
            message: The message content
            agent_manager: Optional AgentManager instance for processing
            progress_callback: Optional callback for progress updates
            tool_callback: Optional callback for tool execution results
            error_callback: Optional callback for error handling

        Returns:
            Message: The stored user message

        Raises:
            SessionNotFoundError: If the session doesn't exist
        """
        logger.info(f"Sending message to session {session_id}: {message[:100]}...")

        # Validate session exists and is active
        session = await self.get_session(session_id)

        if session.status != SessionStatus.ACTIVE:
            raise SessionStateError(
                f"Cannot send message to session with status: {session.status}"
            )

        # Store the user message using MessageManager
        from app.core.message_manager import message_manager

        stored_message = await message_manager.store_user_message(
            session_id=session_id, content=message
        )

        # If agent manager is provided, process the message
        if agent_manager:
            try:
                await agent_manager.process_message(
                    session_id=session_id,
                    message=message,
                    progress_callback=progress_callback,
                    tool_callback=tool_callback,
                    error_callback=error_callback,
                )
                logger.info(f"Message processed successfully for session {session_id}")
            except Exception as e:
                logger.error(
                    f"Failed to process message for session {session_id}: {str(e)}"
                )
                # Update session status to failed if agent processing fails
                await self.update_session_status(session_id, SessionStatus.FAILED)
                raise
        else:
            # Fallback behavior - just log the message
            logger.info(
                f"Message queued for processing in session {session_id} (no agent manager provided)"
            )

        return stored_message

    async def get_chat_history(
        self,
        session_id: str,
        limit: int = 100,
        pagination: Optional[PaginationParams] = None,
        role_filter: Optional[MessageRole] = None,
    ) -> MessageListResponse:
        """
        Get chat history for a session with enhanced pagination and filtering.

        Args:
            session_id: The session ID to get history for
            limit: Maximum number of messages to retrieve (for backward compatibility)
            pagination: Optional pagination parameters (overrides limit)
            role_filter: Optional role filter

        Returns:
            MessageListResponse: Paginated list of messages

        Raises:
            SessionNotFoundError: If the session doesn't exist
        """
        logger.debug(
            f"Retrieving chat history for session {session_id} (limit: {limit})"
        )

        # Validate session exists
        await self.get_session(session_id)

        # Use MessageManager for enhanced chat history retrieval
        from app.core.message_manager import message_manager

        # If pagination is not provided, create one from limit for backward compatibility
        if pagination is None:
            pagination = PaginationParams(page=1, page_size=limit)

        return await message_manager.get_chat_history(
            session_id=session_id, pagination=pagination, role_filter=role_filter
        )

    def _is_valid_status_transition(
        self, current: SessionStatus, new: SessionStatus
    ) -> bool:
        """
        Check if a status transition is valid.

        Args:
            current: Current session status
            new: New session status

        Returns:
            bool: True if transition is valid
        """
        if current == new:
            return True  # Same status is always valid

        valid_transitions = self._valid_status_transitions.get(current, [])
        return new in valid_transitions
