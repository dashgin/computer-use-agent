"""
Session management REST API endpoints.

This module implements all session-related REST endpoints including:
- Session CRUD operations (create, read, update, delete)
- Session listing with pagination and filtering
- Session status management
"""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import SessionManagerDep
from app.core.logging import get_logger
from app.core.session_manager import (
    SessionNotFoundError,
    SessionStateError,
)
from app.models.schemas import (
    CreateSessionRequest,
    PaginationParams,
    Session,
    SessionListResponse,
    SessionStatus,
    SortParams,
    UpdateSessionRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post(
    "",
    response_model=Session,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new session",
    description="Create a new computer use agent session with optional title and metadata",
)
async def create_session(
    request: CreateSessionRequest,
    session_manager: SessionManagerDep,
) -> Session:
    """
    Create a new session.

    Args:
        request: Session creation request with title and metadata
        session_manager: Session manager dependency

    Returns:
        Session: The created session object

    Raises:
        HTTPException: If session creation fails
    """
    try:
        logger.info(f"Creating new session with title: {request.title}")

        session = await session_manager.create_session(
            title=request.title, metadata=request.metadata
        )

        logger.info(f"Successfully created session: {session.id}")
        return session

    except ValueError as e:
        logger.error(f"Session creation validation error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Session creation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session",
        )


@router.get(
    "",
    response_model=SessionListResponse,
    summary="list sessions",
    description="list all sessions with pagination, sorting, and optional status filtering",
)
async def list_sessions(
    session_manager: SessionManagerDep,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    status_filter: SessionStatus | None = None,
) -> SessionListResponse:
    """
    list sessions with pagination and filtering.

    Args:
        page: Page number (1-based)
        page_size: Number of items per page
        sort_by: Field to sort by
        sort_order: Sort order (asc/desc)
        status_filter: Optional status_filter filter
        session_manager: Session manager dependency

    Returns:
        SessionListResponse: Paginated list of sessions

    Raises:
        HTTPException: If listing fails
    """
    try:
        logger.debug(
            f"Listing sessions - page: {page}, size: {page_size}, status_filter: {status_filter}"
        )

        pagination = PaginationParams(page=page, page_size=page_size)
        sort_params = SortParams(sort_by=sort_by, sort_order=sort_order)

        response = await session_manager.list_sessions(
            pagination=pagination, sort=sort_params, status_filter=status_filter
        )

        logger.debug(
            f"Listed {len(response.sessions)} sessions (total: {response.total})"
        )
        return response

    except ValueError as e:
        logger.error(f"Session listing validation error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Session listing failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list sessions",
        )


@router.get(
    "/{session_id}",
    response_model=Session,
    summary="Get session details",
    description="Retrieve detailed information about a specific session",
)
async def get_session(session_id: str, session_manager: SessionManagerDep) -> Session:
    """
    Get session details by ID.

    Args:
        session_id: The session ID to retrieve
        session_manager: Session manager dependency

    Returns:
        Session: The session object

    Raises:
        HTTPException: If session not found or retrieval fails
    """
    try:
        logger.debug(f"Getting session details: {session_id}")

        session = await session_manager.get_session(session_id)

        logger.debug(f"Retrieved session: {session_id}")
        return session

    except SessionNotFoundError:
        logger.warning(f"Session not found: {session_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    except Exception as e:
        logger.error(f"Failed to get session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session",
        )


@router.put(
    "/{session_id}",
    response_model=Session,
    summary="Update session",
    description="Update session title, status, or metadata",
)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    session_manager: SessionManagerDep,
) -> Session:
    """
    Update session details.

    Args:
        session_id: The session ID to update
        request: Update request with new values
        session_manager: Session manager dependency

    Returns:
        Session: The updated session object

    Raises:
        HTTPException: If session not found, invalid state transition, or update fails
    """
    try:
        logger.info(f"Updating session: {session_id}")

        session = await session_manager.update_session(
            session_id=session_id,
            title=request.title,
            status=request.status,
            metadata=request.metadata,
        )

        logger.info(f"Successfully updated session: {session_id}")
        return session

    except SessionNotFoundError:
        logger.warning(f"Session not found for update: {session_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    except SessionStateError as e:
        logger.warning(f"Invalid session state transition: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        logger.error(f"Session update validation error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update session",
        )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete session",
    description="Delete a session and all associated data",
)
async def delete_session(session_id: str, session_manager: SessionManagerDep):
    """
    Delete a session.

    Args:
        session_id: The session ID to delete
        session_manager: Session manager dependency

    Raises:
        HTTPException: If session not found or deletion fails
    """
    try:
        logger.info(f"Deleting session: {session_id}")

        deleted = await session_manager.delete_session(session_id)

        if not deleted:
            logger.warning(f"Session not found for deletion: {session_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        logger.info(f"Successfully deleted session: {session_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete session",
        )


@router.get(
    "/{session_id}/status",
    response_model=dict,
    summary="Get session status",
    description="Get the current status of a session",
)
async def get_session_status(
    session_id: str, session_manager: SessionManagerDep
) -> dict:
    """
    Get session status.

    Args:
        session_id: The session ID to check
        session_manager: Session manager dependency

    Returns:
        dict: Session status information

    Raises:
        HTTPException: If session not found or status check fails
    """
    try:
        logger.debug(f"Getting session status: {session_id}")

        session = await session_manager.get_session(session_id)

        return {
            "session_id": session.id,
            "status": session.status,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    except SessionNotFoundError:
        logger.warning(f"Session not found for status check: {session_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    except Exception as e:
        logger.error(f"Failed to get session status {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session status",
        )
