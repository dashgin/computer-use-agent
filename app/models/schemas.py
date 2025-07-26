"""
Pydantic models for API validation and data transfer objects.

This module defines all request/response models for API endpoints,
internal communication DTOs, and comprehensive validation rules.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# Enums for validation
class SessionStatus(str, Enum):
    """Valid session status values."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class MessageRole(str, Enum):
    """Valid message role values."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ContentType(str, Enum):
    """Valid content type values."""

    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


class ExecutionStatus(str, Enum):
    """Valid tool execution status values."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class UpdateType(str, Enum):
    """Valid progress update types."""

    MESSAGE = "message"
    TOOL_START = "tool_start"
    TOOL_COMPLETE = "tool_complete"
    ERROR = "error"
    SESSION_STATUS = "session_status"


# Core Data Models
class SessionBase(BaseModel):
    """Base session model with common fields."""

    title: Optional[str] = Field(None, max_length=200, description="Session title")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Session metadata"
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Title cannot be empty string")
        return v.strip() if v else v

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v):
        if not isinstance(v, dict):
            raise ValueError("Metadata must be a dictionary")
        # Ensure metadata values are JSON serializable
        try:
            import json

            json.dumps(v)
        except (TypeError, ValueError):
            raise ValueError("Metadata must contain JSON serializable values")
        return v


class Session(SessionBase):
    """Complete session model for responses."""

    id: str = Field(..., description="Unique session identifier")
    created_at: datetime = Field(..., description="Session creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    status: SessionStatus = Field(
        SessionStatus.ACTIVE, description="Current session status"
    )

    class Config:
        from_attributes = True
        # Map database field names to Pydantic field names
        populate_by_name = True

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Custom validation to handle database field mapping."""
        if hasattr(obj, "session_metadata"):
            # Convert database object to dict and map field names
            data = {
                "id": obj.id,
                "created_at": obj.created_at,
                "updated_at": obj.updated_at,
                "status": obj.status,
                "title": obj.title,
                "metadata": obj.session_metadata,
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


class MessageBase(BaseModel):
    """Base message model with common fields."""

    content: str = Field(
        ..., min_length=1, max_length=50000, description="Message content"
    )
    content_type: ContentType = Field(ContentType.TEXT, description="Content type")
    tool_use_id: Optional[str] = Field(None, description="Associated tool use ID")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Message metadata"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Content cannot be empty")
        return v

    @field_validator("tool_use_id")
    @classmethod
    def validate_tool_use_id(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Tool use ID cannot be empty string")
        return v


class Message(MessageBase):
    """Complete message model for responses."""

    id: int = Field(..., description="Message ID")
    session_id: str = Field(..., description="Associated session ID")
    role: MessageRole = Field(..., description="Message role")
    timestamp: datetime = Field(..., description="Message timestamp")

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Custom validation to handle database field mapping."""
        if hasattr(obj, "message_metadata"):
            # Convert database object to dict and map field names
            data = {
                "id": obj.id,
                "session_id": obj.session_id,
                "role": obj.role,
                "content": obj.content,
                "content_type": obj.content_type,
                "tool_use_id": obj.tool_use_id,
                "timestamp": obj.timestamp,
                "metadata": obj.message_metadata,
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


class ToolExecutionBase(BaseModel):
    """Base tool execution model with common fields."""

    tool_name: str = Field(..., min_length=1, max_length=100, description="Tool name")
    tool_input: dict[str, Any] = Field(..., description="Tool input parameters")
    tool_output: Optional[dict[str, Any]] = Field(
        None, description="Tool output results"
    )
    error_message: Optional[str] = Field(
        None, max_length=5000, description="Error message if failed"
    )

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Tool name cannot be empty")
        return v.strip()

    @field_validator("tool_input")
    @classmethod
    def validate_tool_input(cls, v):
        if not isinstance(v, dict):
            raise ValueError("Tool input must be a dictionary")
        return v


class ToolExecution(ToolExecutionBase):
    """Complete tool execution model for responses."""

    id: str = Field(..., description="Tool execution ID")
    session_id: str = Field(..., description="Associated session ID")
    message_id: int = Field(..., description="Associated message ID")
    status: ExecutionStatus = Field(
        ExecutionStatus.PENDING, description="Execution status"
    )
    started_at: datetime = Field(..., description="Execution start timestamp")
    completed_at: Optional[datetime] = Field(
        None, description="Execution completion timestamp"
    )

    class Config:
        from_attributes = True


# API Request Models
class CreateSessionRequest(SessionBase):
    """Request model for creating a new session."""


class SendMessageRequest(BaseModel):
    """Request model for sending a message to a session."""

    content: str = Field(
        ..., min_length=1, max_length=50000, description="Message content"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Message content cannot be empty")
        return v.strip()


class UpdateSessionRequest(BaseModel):
    """Request model for updating session metadata."""

    title: Optional[str] = Field(
        None, max_length=200, description="Updated session title"
    )
    status: Optional[SessionStatus] = Field(None, description="Updated session status")
    metadata: Optional[dict[str, Any]] = Field(
        None, description="Updated session metadata"
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Title cannot be empty string")
        return v.strip() if v else v

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if not any([self.title, self.status, self.metadata]):
            raise ValueError("At least one field must be provided for update")
        return self


# API Response Models
class SessionListResponse(BaseModel):
    """Response model for listing sessions."""

    sessions: list[Session] = Field(..., description="list of sessions")
    total: int = Field(..., ge=0, description="Total number of sessions")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page")
    has_next: bool = Field(..., description="Whether there are more pages")


class MessageListResponse(BaseModel):
    """Response model for listing messages."""

    messages: list[Message] = Field(..., description="list of messages")
    total: int = Field(..., ge=0, description="Total number of messages")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page")
    has_next: bool = Field(..., description="Whether there are more pages")


class ToolExecutionListResponse(BaseModel):
    """Response model for listing tool executions."""

    executions: list[ToolExecution] = Field(..., description="list of tool executions")
    total: int = Field(..., ge=0, description="Total number of executions")


# Real-time Communication Models
class ProgressUpdate(BaseModel):
    """Model for real-time progress updates via WebSocket."""

    type: UpdateType = Field(..., description="Update type")
    data: dict[str, Any] = Field(..., description="Update data")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Update timestamp",
    )
    session_id: str = Field(..., description="Associated session ID")

    @field_validator("data")
    @classmethod
    def validate_data(cls, v):
        if not isinstance(v, dict):
            raise ValueError("Update data must be a dictionary")
        return v


class WebSocketMessage(BaseModel):
    """Model for WebSocket message structure."""

    type: str = Field(..., min_length=1, description="Message type")
    payload: dict[str, Any] = Field(..., description="Message payload")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Message timestamp",
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Message type cannot be empty")
        return v.strip()


# VNC Integration Models
class VNCConnectionInfo(BaseModel):
    """Model for VNC connection information."""

    host: str = Field(..., min_length=1, description="VNC server host")
    port: int = Field(..., ge=1, le=65535, description="VNC server port")
    password: Optional[str] = Field(None, description="VNC connection password")
    display: str = Field(..., min_length=1, description="VNC display identifier")
    status: str = Field(..., description="VNC server status")

    @field_validator("host")
    @classmethod
    def validate_host(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Host cannot be empty")
        return v.strip()

    @field_validator("display")
    @classmethod
    def validate_display(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Display cannot be empty")
        return v.strip()


class VNCStatus(BaseModel):
    """Model for VNC server status."""

    is_running: bool = Field(..., description="Whether VNC server is running")
    display: Optional[str] = Field(None, description="Active display")
    port: Optional[int] = Field(None, ge=1, le=65535, description="Active port")
    uptime: Optional[int] = Field(None, ge=0, description="Server uptime in seconds")
    error_message: Optional[str] = Field(
        None, description="Error message if not running"
    )


# Error Response Models
class ErrorResponse(BaseModel):
    """Standard error response model."""

    error_code: str = Field(..., min_length=1, description="Error code")
    message: str = Field(..., min_length=1, description="Human-readable error message")
    details: Optional[dict[str, Any]] = Field(
        None, description="Additional error details"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Error timestamp",
    )
    request_id: Optional[str] = Field(None, description="Request correlation ID")

    @field_validator("error_code")
    @classmethod
    def validate_error_code(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Error code cannot be empty")
        return v.strip().upper()

    @field_validator("message")
    @classmethod
    def validate_message(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Error message cannot be empty")
        return v.strip()


class ValidationErrorDetail(BaseModel):
    """Model for validation error details."""

    field: str = Field(..., description="Field that failed validation")
    message: str = Field(..., description="Validation error message")
    invalid_value: Any = Field(None, description="The invalid value that was provided")


class ValidationErrorResponse(ErrorResponse):
    """Extended error response for validation errors."""

    validation_errors: list[ValidationErrorDetail] = Field(
        ..., description="list of validation errors"
    )


# Health Check Models
class HealthCheckResponse(BaseModel):
    """Model for health check responses."""

    status: str = Field(..., description="Overall health status")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Health check timestamp",
    )
    version: str = Field(..., description="Application version")
    components: dict[str, dict[str, Any]] = Field(
        ..., description="Component health status"
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        valid_statuses = ["healthy", "degraded", "unhealthy"]
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        return v


# Pagination Models
class PaginationParams(BaseModel):
    """Model for pagination parameters."""

    page: int = Field(1, ge=1, description="Page number (1-based)")
    page_size: int = Field(20, ge=1, le=100, description="Number of items per page")


class SortParams(BaseModel):
    """Model for sorting parameters."""

    sort_by: str = Field("created_at", description="Field to sort by")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="Sort order")

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v):
        valid_fields = ["created_at", "updated_at", "title", "status"]
        if v not in valid_fields:
            raise ValueError(f"Sort field must be one of: {valid_fields}")
        return v


# Internal Communication DTOs
class SessionCreateDTO(BaseModel):
    """Internal DTO for session creation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Session ID")
    title: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: SessionStatus = SessionStatus.ACTIVE


class MessageCreateDTO(BaseModel):
    """Internal DTO for message creation."""

    session_id: str
    role: MessageRole
    content: str
    content_type: ContentType = ContentType.TEXT
    tool_use_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionCreateDTO(BaseModel):
    """Internal DTO for tool execution creation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    message_id: int
    tool_name: str
    tool_input: dict[str, Any]
    status: ExecutionStatus = ExecutionStatus.PENDING
