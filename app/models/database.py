"""
Database models for the computer use session backend.

This module defines SQLAlchemy models for sessions, messages, and tool executions
that correspond to the database schema outlined in the design document.
"""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Session(Base):
    """
    SQLAlchemy model for chat sessions.

    Represents a computer use agent session with metadata and lifecycle tracking.
    """

    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )
    status = Column(String, default="active", nullable=False)
    title = Column(String, nullable=True)
    session_metadata = Column(JSON, default=dict, nullable=False)

    # Relationships
    messages = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )
    tool_executions = relationship(
        "ToolExecution", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<Session(id='{self.id}', status='{self.status}', title='{self.title}')>"
        )


class Message(Base):
    """
    SQLAlchemy model for chat messages.

    Stores all messages in a session including user messages, assistant responses,
    and tool-related messages with proper role and content type tracking.
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String, nullable=False)  # 'user', 'assistant', 'tool'
    content = Column(Text, nullable=False)
    content_type = Column(
        String, default="text", nullable=False
    )  # 'text', 'tool_use', 'tool_result'
    tool_use_id = Column(String, nullable=True)
    timestamp = Column(DateTime, default=func.now(), nullable=False)
    message_metadata = Column(JSON, default=dict, nullable=False)

    # Relationships
    session = relationship("Session", back_populates="messages")
    tool_executions = relationship(
        "ToolExecution", back_populates="message", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Message(id={self.id}, session_id='{self.session_id}', role='{self.role}')>"


class ToolExecution(Base):
    """
    SQLAlchemy model for tool executions.

    Tracks individual tool calls made by the agent including input, output,
    status, and timing information for debugging and monitoring.
    """

    __tablename__ = "tool_executions"

    id = Column(String, primary_key=True)
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    message_id = Column(
        Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    tool_name = Column(String, nullable=False)
    tool_input = Column(JSON, nullable=False)
    tool_output = Column(JSON, nullable=True)
    status = Column(
        String, default="pending", nullable=False
    )  # 'pending', 'running', 'completed', 'failed'
    started_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    session = relationship("Session", back_populates="tool_executions")
    message = relationship("Message", back_populates="tool_executions")

    def __repr__(self):
        return f"<ToolExecution(id='{self.id}', tool_name='{self.tool_name}', status='{self.status}')>"
