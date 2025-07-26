"""
Agent integration layer for computer use session backend.

This module implements the AgentManager class that wraps the existing computer use agent loop,
handles message processing and routing, and provides callback system for progress updates
and tool execution results while maintaining compatibility with the existing loop.py.
"""

import asyncio
import uuid
from collections.abc import Callable as CallableABC
from datetime import datetime
from typing import Any, Callable, Optional

from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaTextBlockParam,
)

from app.core.logging import get_logger
from app.models.database import (
    Message as MessageModel,
    ToolExecution as ToolExecutionModel,
)
from app.models.schemas import (
    ProgressUpdate,
    UpdateType,
)

# Import the existing computer use agent components
from computer_use_demo.loop import APIProvider, sampling_loop
from computer_use_demo.tools import ToolResult
from computer_use_demo.tools.groups import ToolVersion

logger = get_logger(__name__)


class AgentExecutionError(Exception):
    """Raised when agent execution encounters an error."""


class AgentManager:
    """
    Manages computer use agent integration and execution.

    This class wraps the existing computer use agent loop and provides:
    - Message processing and routing to the agent
    - Callback system for progress updates and tool execution results
    - Integration with existing loop.py while maintaining compatibility
    - Session-aware agent execution with proper state management
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        provider: APIProvider = APIProvider.ANTHROPIC,
        max_tokens: int = 4096,
        tool_version: ToolVersion = "computer_use_20241022",
        system_prompt_suffix: str = "",
        only_n_most_recent_images: Optional[int] = None,
        thinking_budget: Optional[int] = None,
        token_efficient_tools_beta: bool = False,
    ):
        """
        Initialize the AgentManager with configuration.

        Args:
            api_key: Anthropic API key
            model: Model name to use
            provider: API provider (anthropic, bedrock, vertex)
            max_tokens: Maximum tokens per request
            tool_version: Tool version to use
            system_prompt_suffix: Additional system prompt text
            only_n_most_recent_images: Limit on recent images to keep
            thinking_budget: Token budget for thinking
            token_efficient_tools_beta: Enable token efficient tools beta
        """
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self.max_tokens = max_tokens
        self.tool_version = tool_version
        self.system_prompt_suffix = system_prompt_suffix
        self.only_n_most_recent_images = only_n_most_recent_images
        self.thinking_budget = thinking_budget
        self.token_efficient_tools_beta = token_efficient_tools_beta

        # Track active sessions and their callbacks
        self._active_sessions: dict[str, dict[str, Any]] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}

        logger.info("AgentManager initialized with model: %s", model)

    async def process_message(
        self,
        session_id: str,
        message: str,
        progress_callback: Optional[Callable[[ProgressUpdate], None]] = None,
        tool_callback: Optional[Callable[[ToolResult, str], None]] = None,
        error_callback: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        Process a user message through the agent for a specific session.

        Args:
            session_id: The session ID to process message for
            message: The user message content
            progress_callback: Optional callback for progress updates
            tool_callback: Optional callback for tool execution results
            error_callback: Optional callback for error handling

        Raises:
            AgentExecutionError: If agent execution fails
        """
        logger.info(f"Processing message for session {session_id}: {message[:100]}...")

        try:
            # Get or create session lock
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()

            async with self._session_locks[session_id]:
                # Use a single database session for the entire operation
                from app.db.connection import db_manager

                async with db_manager.async_session_maker() as db_session:
                    try:
                        # User message will be stored by SessionManager through MessageManager
                        # No need to store it here again to avoid duplication

                        # Get conversation history
                        messages = await self._get_conversation_history_with_session(
                            db_session, session_id
                        )

                        # Commit the message storage before executing agent loop
                        await db_session.commit()

                        # set up callbacks for this session
                        output_callback, tool_output_callback, api_response_callback = (
                            self._setup_callbacks(
                                session_id,
                                progress_callback,
                                tool_callback,
                                error_callback,
                            )
                        )

                        # Execute agent loop
                        await self._execute_agent_loop(
                            session_id,
                            messages,
                            output_callback,
                            tool_output_callback,
                            api_response_callback,
                        )

                    except Exception:
                        await db_session.rollback()
                        raise

        except Exception as e:
            logger.error(
                f"Failed to process message for session {session_id}: {str(e)}"
            )
            if error_callback:
                error_callback(e)
            raise AgentExecutionError(f"Agent execution failed: {str(e)}") from e

    async def _execute_agent_loop(
        self,
        session_id: str,
        messages: list[BetaMessageParam],
        output_callback: CallableABC[[BetaContentBlockParam], None],
        tool_output_callback: CallableABC[[ToolResult, str], None],
        api_response_callback: CallableABC[[Any, Any, Any], None],
    ) -> None:
        """
        Execute the agent loop with the provided messages and callbacks.

        Args:
            session_id: Session ID for tracking
            messages: Conversation history in Anthropic format
            output_callback: Callback for agent output
            tool_output_callback: Callback for tool results
            api_response_callback: Callback for API responses
        """
        logger.debug(
            f"Executing agent loop for session {session_id} with {len(messages)} messages"
        )

        try:
            # Call the existing sampling loop
            final_messages = await sampling_loop(
                model=self.model,
                provider=self.provider,
                system_prompt_suffix=self.system_prompt_suffix,
                messages=messages,
                output_callback=output_callback,
                tool_output_callback=tool_output_callback,
                api_response_callback=api_response_callback,
                api_key=self.api_key,
                only_n_most_recent_images=self.only_n_most_recent_images,
                max_tokens=self.max_tokens,
                tool_version=self.tool_version,
                thinking_budget=self.thinking_budget,
                token_efficient_tools_beta=self.token_efficient_tools_beta,
            )

            # Store final messages in database using MessageManager
            await self._store_agent_messages_enhanced(
                session_id, final_messages, len(messages)
            )

            logger.info(f"Agent loop completed for session {session_id}")

        except Exception as e:
            logger.error(f"Agent loop failed for session {session_id}: {str(e)}")
            raise

    def _setup_callbacks(
        self,
        session_id: str,
        progress_callback: Optional[Callable[[ProgressUpdate], None]] = None,
        tool_callback: Optional[Callable[[ToolResult, str], None]] = None,
        error_callback: Optional[Callable[[Exception], None]] = None,
    ) -> tuple[CallableABC, CallableABC, CallableABC]:
        """
        set up callback functions for the agent loop.

        Args:
            session_id: Session ID for tracking
            progress_callback: Optional progress update callback
            tool_callback: Optional tool execution callback
            error_callback: Optional error callback

        Returns:
            tuple of callbacks for output, tool output, and API response
        """

        def output_callback(content_block: BetaContentBlockParam) -> None:
            """Handle agent output content blocks."""
            try:
                logger.debug(
                    f"Agent output for session {session_id}: {content_block.get('type', 'unknown')}"
                )

                if progress_callback:
                    update = ProgressUpdate(
                        type=UpdateType.MESSAGE,
                        data={"content_block": content_block, "session_id": session_id},
                        session_id=session_id,
                    )
                    progress_callback(update)

            except Exception as e:
                logger.error(
                    f"Error in output callback for session {session_id}: {str(e)}"
                )
                if error_callback:
                    error_callback(e)

        def tool_output_callback(result: ToolResult, tool_use_id: str) -> None:
            """Handle tool execution results."""
            try:
                logger.debug(
                    f"Tool execution result for session {session_id}: {result.output[:100] if result.output else 'No output'}..."
                )

                # Store tool execution in database
                asyncio.create_task(
                    self._store_tool_execution(session_id, result, tool_use_id)
                )

                if tool_callback:
                    tool_callback(result, tool_use_id)

                if progress_callback:
                    update = ProgressUpdate(
                        type=UpdateType.TOOL_COMPLETE,
                        data={
                            "tool_use_id": tool_use_id,
                            "result": {
                                "output": result.output,
                                "error": result.error,
                                "base64_image": result.base64_image is not None,
                                "system": result.system,
                            },
                            "session_id": session_id,
                        },
                        session_id=session_id,
                    )
                    progress_callback(update)

            except Exception as e:
                logger.error(
                    f"Error in tool output callback for session {session_id}: {str(e)}"
                )
                if error_callback:
                    error_callback(e)

        def api_response_callback(request: Any, response: Any, error: Any) -> None:
            """Handle API response information."""
            try:
                if error:
                    logger.warning(f"API error for session {session_id}: {str(error)}")
                    if error_callback:
                        error_callback(error)
                else:
                    logger.debug(f"API response received for session {session_id}")

            except Exception as e:
                logger.error(
                    f"Error in API response callback for session {session_id}: {str(e)}"
                )
                if error_callback:
                    error_callback(e)

        return output_callback, tool_output_callback, api_response_callback

    async def _get_conversation_history(
        self, session_id: str
    ) -> list[BetaMessageParam]:
        """
        Retrieve conversation history for a session in Anthropic format.

        Args:
            session_id: Session ID to get history for

        Returns:
            list of messages in Anthropic BetaMessageParam format
        """
        from app.db.connection import db_manager

        async with db_manager.async_session_maker() as db_session:
            return await self._get_conversation_history_with_session(
                db_session, session_id
            )

    async def _get_conversation_history_with_session(
        self, db_session, session_id: str
    ) -> list[BetaMessageParam]:
        """
        Retrieve conversation history for a session using provided database session.

        Args:
            db_session: Database session to use
            session_id: Session ID to get history for

        Returns:
            list of messages in Anthropic BetaMessageParam format
        """
        logger.debug(f"Retrieving conversation history for session {session_id}")

        # Get messages ordered by timestamp
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        query = (
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.timestamp)
            .options(selectinload(MessageModel.tool_executions))
        )

        result = await db_session.execute(query)
        message_models = result.scalars().all()

        # Convert to Anthropic format
        messages = []
        for msg in message_models:
            if msg.role == "user":
                messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                # Parse assistant content which may include tool uses
                content = self._parse_assistant_content(msg)
                if content:
                    messages.append({"role": "assistant", "content": content})
            elif msg.role == "tool":
                # Tool results are handled as part of assistant messages
                continue

        logger.debug(
            f"Retrieved {len(messages)} formatted messages for session {session_id}"
        )
        return messages

    def _parse_assistant_content(
        self, message: MessageModel
    ) -> list[BetaContentBlockParam]:
        """
        Parse assistant message content into Anthropic format.

        Args:
            message: Database message model

        Returns:
            list of content blocks in Anthropic format
        """
        content_blocks = []

        if message.content_type == "text":
            content_blocks.append({"type": "text", "text": message.content})
        elif message.content_type == "tool_use":
            # Parse tool use from content
            try:
                import json

                tool_data = json.loads(message.content)
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": message.tool_use_id,
                        "name": tool_data.get("name", "unknown"),
                        "input": tool_data.get("input", {}),
                    }
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse tool use content: {str(e)}")
                # Fallback to text content
                content_blocks.append({"type": "text", "text": message.content})

        return content_blocks

    async def _store_user_message(self, session_id: str, content: str) -> None:
        """
        Store a user message in the database.

        Args:
            session_id: Session ID
            content: Message content
        """
        from app.db.connection import db_manager

        async with db_manager.async_session_maker() as db_session:
            try:
                await self._store_user_message_with_session(
                    db_session, session_id, content
                )
                await db_session.commit()
            except Exception:
                await db_session.rollback()
                raise

    async def _store_user_message_with_session(
        self, db_session, session_id: str, content: str
    ) -> None:
        """
        Store a user message in the database using provided session.

        Args:
            db_session: Database session to use
            session_id: Session ID
            content: Message content
        """
        try:
            message = MessageModel(
                session_id=session_id,
                role="user",
                content=content,
                content_type="text",
                message_metadata={},
            )

            db_session.add(message)
            await db_session.flush()  # Flush to make it visible in the same session

            logger.debug(f"Stored user message for session {session_id}")

        except Exception as e:
            logger.error(
                f"Failed to store user message for session {session_id}: {str(e)}"
            )
            raise

    async def _store_agent_messages_enhanced(
        self, session_id: str, messages: list[BetaMessageParam], start_index: int
    ) -> None:
        """
        Store new agent messages from the conversation using MessageManager.

        Args:
            session_id: Session ID
            messages: Full conversation history
            start_index: Index to start storing from (to avoid duplicates)
        """
        import json

        from app.core.message_manager import message_manager
        from app.models.schemas import ContentType

        try:
            # Store only new messages (after start_index)
            new_messages = messages[start_index:]

            for msg in new_messages:
                if msg["role"] == "assistant":
                    # Store assistant message with content blocks
                    for content_block in msg["content"]:
                        if content_block["type"] == "text":
                            await message_manager.store_assistant_message(
                                session_id=session_id,
                                content=content_block["text"],
                                content_type=ContentType.TEXT,
                            )

                        elif content_block["type"] == "tool_use":
                            # Store tool use as a message
                            tool_data = {
                                "name": content_block["name"],
                                "input": content_block["input"],
                            }

                            await message_manager.store_assistant_message(
                                session_id=session_id,
                                content=json.dumps(tool_data),
                                content_type=ContentType.TOOL_USE,
                                tool_use_id=content_block["id"],
                            )

                elif msg["role"] == "user" and isinstance(msg["content"], list):
                    # Handle tool results
                    for content_block in msg["content"]:
                        if content_block.get("type") == "tool_result":
                            await message_manager.store_tool_message(
                                session_id=session_id,
                                tool_result=str(content_block.get("content", "")),
                                tool_use_id=content_block.get("tool_use_id"),
                                metadata={
                                    "is_error": content_block.get("is_error", False)
                                },
                            )

            logger.debug(
                f"Stored {len(new_messages)} new messages for session {session_id} using MessageManager"
            )

        except Exception as e:
            logger.error(
                f"Failed to store agent messages for session {session_id}: {str(e)}"
            )
            raise

    async def _store_agent_messages(
        self, session_id: str, messages: list[BetaMessageParam], start_index: int
    ) -> None:
        """
        Legacy compatibility wrapper - delegates to enhanced message storage.
        """
        await self._store_agent_messages_enhanced(session_id, messages, start_index)

    async def _store_tool_execution(
        self, session_id: str, result: ToolResult, tool_use_id: str
    ) -> None:
        """
        Store tool execution result in the database.

        Args:
            session_id: Session ID
            result: Tool execution result
            tool_use_id: Tool use ID
        """
        from app.db.connection import db_manager

        async with db_manager.async_session_maker() as db_session:
            try:
                # Find the associated message
                from sqlalchemy import select

                query = (
                    select(MessageModel)
                    .where(MessageModel.session_id == session_id)
                    .where(MessageModel.tool_use_id == tool_use_id)
                    .order_by(MessageModel.timestamp.desc())
                )

                result_msg = await db_session.execute(query)
                message = result_msg.scalar_one_or_none()

                if not message:
                    logger.warning(
                        f"No message found for tool_use_id {tool_use_id} in session {session_id}"
                    )
                    return

                # Create tool execution record
                tool_execution = ToolExecutionModel(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_id=message.id,
                    tool_name=getattr(result, "tool_name", "unknown"),
                    tool_input=getattr(result, "tool_input", {}),
                    tool_output={
                        "output": result.output,
                        "error": result.error,
                        "base64_image": result.base64_image is not None,
                        "system": result.system,
                    },
                    status="completed" if not result.error else "failed",
                    # Let database handle started_at with its default
                    completed_at=datetime.now(),  # timezone-naive to match database
                    error_message=result.error,
                )

                db_session.add(tool_execution)
                await db_session.commit()

                logger.debug(
                    f"Stored tool execution for session {session_id}, tool_use_id {tool_use_id}"
                )

            except Exception as e:
                await db_session.rollback()
                logger.error(
                    f"Failed to store tool execution for session {session_id}: {str(e)}"
                )
                # Don't raise here as this is not critical for agent execution

    async def stop_session(self, session_id: str) -> None:
        """
        Stop agent execution for a session.

        Args:
            session_id: Session ID to stop
        """
        logger.info(f"Stopping agent execution for session {session_id}")

        if session_id in self._active_sessions:
            # Mark session as stopped
            self._active_sessions[session_id]["stopped"] = True

        # Clean up session lock
        if session_id in self._session_locks:
            del self._session_locks[session_id]

        logger.info(f"Agent execution stopped for session {session_id}")

    def is_session_active(self, session_id: str) -> bool:
        """
        Check if a session has active agent execution.

        Args:
            session_id: Session ID to check

        Returns:
            bool: True if session is actively executing
        """
        return session_id in self._active_sessions and not self._active_sessions[
            session_id
        ].get("stopped", False)

    async def get_session_status(self, session_id: str) -> dict[str, Any]:
        """
        Get status information for a session.

        Args:
            session_id: Session ID to get status for

        Returns:
            dict with session status information
        """
        return {
            "session_id": session_id,
            "is_active": self.is_session_active(session_id),
            "has_lock": session_id in self._session_locks,
            "agent_config": {
                "model": self.model,
                "provider": self.provider,
                "tool_version": self.tool_version,
                "max_tokens": self.max_tokens,
            },
        }

    async def process_message_simple(
        self,
        session_id: str,
        message: str,
        progress_callback: Optional[Callable] = None,
    ) -> None:
        """
        Process a user message through the computer use agent using sampling_loop.
        Used for WebSocket integration with real-time streaming.

        Args:
            session_id: Session ID to process message for
            message: User message to process
            progress_callback: Optional callback for progress updates
        """
        try:
            # Get conversation history for this session
            messages = await self._get_conversation_history(session_id)

            # Add the new user message
            messages.append(
                {
                    "role": "user",
                    "content": [BetaTextBlockParam(type="text", text=message)],
                }
            )

            # Set up callbacks for real-time streaming
            output_callback = self._create_output_callback(
                session_id, progress_callback
            )
            tool_output_callback = self._create_tool_output_callback(
                session_id, progress_callback
            )
            api_response_callback = self._create_api_response_callback(
                session_id, progress_callback
            )

            # Run the sampling loop with real-time callbacks
            updated_messages = await sampling_loop(
                model=self.model,
                provider=self.provider,
                system_prompt_suffix=self.system_prompt_suffix,
                messages=messages,
                output_callback=output_callback,
                tool_output_callback=tool_output_callback,
                api_response_callback=api_response_callback,
                api_key=self.api_key,
                only_n_most_recent_images=self.only_n_most_recent_images,
                max_tokens=self.max_tokens,
                tool_version=self.tool_version,
                thinking_budget=self.thinking_budget,
                token_efficient_tools_beta=self.token_efficient_tools_beta,
            )

            # Store the new messages that were added during processing
            await self._save_new_messages(session_id, messages, updated_messages)

            logger.info(f"Agent processing completed for session {session_id}")

        except Exception as e:
            logger.error(f"Error in simple message processing: {str(e)}")
            if progress_callback:
                await progress_callback(
                    {
                        "type": "error",
                        "content": f"I encountered an error while processing your message: {str(e)}",
                    }
                )

    def _create_output_callback(
        self, session_id: str, progress_callback: Optional[Callable] = None
    ):
        """Create callback for agent output"""

        def callback(content_block: BetaContentBlockParam):
            asyncio.create_task(
                self._handle_output_callback(
                    session_id, content_block, progress_callback
                )
            )

        return callback

    async def _handle_output_callback(
        self,
        session_id: str,
        content_block: BetaContentBlockParam,
        progress_callback: Optional[Callable] = None,
    ):
        """Handle agent output callback asynchronously"""
        try:
            if content_block["type"] == "text":
                # Stream text content
                text_content = content_block["text"]

                if progress_callback:
                    await progress_callback(
                        {
                            "type": "agent_response",
                            "content": text_content,
                            "role": "assistant",
                        }
                    )

                # Save assistant message to database
                from app.core.message_manager import message_manager

                await message_manager.store_assistant_message(
                    session_id=session_id,
                    content=text_content,
                )

            elif content_block["type"] == "thinking":
                # Stream thinking content
                thinking_content = content_block.get("thinking", "")
                formatted_thinking = f"🤔 **[Thinking]**\n\n{thinking_content}"

                if progress_callback:
                    await progress_callback(
                        {"type": "thinking", "content": formatted_thinking}
                    )

            elif content_block["type"] == "tool_use":
                # Stream tool use information
                tool_name = content_block["name"]
                tool_input = content_block["input"]

                import json

                formatted_input = (
                    json.dumps(tool_input, indent=2) if tool_input else "{}"
                )
                detailed_message = (
                    f"🔧 **Tool: {tool_name}**\n\n```json\n{formatted_input}\n```"
                )

                if progress_callback:
                    await progress_callback(
                        {
                            "type": "tool_use",
                            "content": detailed_message,
                            "tool_name": tool_name,
                            "tool_input": tool_input,
                        }
                    )

                # Save tool use message to database
                from app.core.message_manager import message_manager

                await message_manager.store_assistant_message(
                    session_id=session_id,
                    content=f"Using tool: {tool_name}",
                    tool_use_id=content_block["id"],
                )

        except Exception as e:
            logger.error(f"Error in output callback for session {session_id}: {str(e)}")

    def _create_tool_output_callback(
        self, session_id: str, progress_callback: Optional[Callable] = None
    ):
        """Create callback for tool execution results"""

        def callback(tool_result: ToolResult, tool_use_id: str):
            asyncio.create_task(
                self._handle_tool_output_callback(
                    session_id, tool_result, tool_use_id, progress_callback
                )
            )

        return callback

    async def _handle_tool_output_callback(
        self,
        session_id: str,
        tool_result: ToolResult,
        tool_use_id: str,
        progress_callback: Optional[Callable] = None,
    ):
        """Handle tool output callback asynchronously"""
        try:
            # Build detailed message parts for rich display
            message_parts = []

            if tool_result.output:
                # Check if it's CLI output
                if any(
                    indicator in tool_result.output.lower()
                    for indicator in [
                        "/usr/",
                        "/bin/",
                        "$",
                        "command",
                        "error:",
                        "warning:",
                    ]
                ):
                    message_parts.append(
                        f"📋 **Output:**\n```bash\n{tool_result.output}\n```"
                    )
                else:
                    message_parts.append(f"📋 **Output:**\n{tool_result.output}")

            if tool_result.error:
                message_parts.append(f"❌ **Error:**\n```\n{tool_result.error}\n```")

            if tool_result.base64_image:
                message_parts.append("📸 **Screenshot captured** (see below)")

            # Combine all parts
            detailed_content = (
                "\n\n".join(message_parts)
                if message_parts
                else "✅ Tool executed successfully"
            )

            if progress_callback:
                await progress_callback(
                    {
                        "type": "tool_result",
                        "content": detailed_content,
                        "tool_output": tool_result.output,
                        "tool_error": tool_result.error,
                        "base64_image": tool_result.base64_image,
                    }
                )

            # Save tool result to database
            from app.core.message_manager import message_manager

            await message_manager.store_tool_message(
                session_id=session_id,
                tool_result=tool_result.output or tool_result.error or "Tool executed",
                tool_use_id=tool_use_id,
                metadata={
                    "tool_output": tool_result.output,
                    "tool_error": tool_result.error,
                    "base64_image": tool_result.base64_image,
                    "is_error": bool(tool_result.error),
                },
            )

        except Exception as e:
            logger.error(
                f"Error in tool output callback for session {session_id}: {str(e)}"
            )

    def _create_api_response_callback(
        self, session_id: str, progress_callback: Optional[Callable] = None
    ):
        """Create callback for API responses (for debugging)"""

        def callback(request, response, error):
            if error:
                asyncio.create_task(
                    self._handle_api_error(session_id, error, progress_callback)
                )

        return callback

    async def _handle_api_error(
        self,
        session_id: str,
        error: Exception,
        progress_callback: Optional[Callable] = None,
    ):
        """Handle API errors"""
        error_message = f"API Error: {str(error)}"
        logger.error(f"API error for session {session_id}: {error_message}")

        if progress_callback:
            await progress_callback({"type": "error", "content": error_message})

    async def _save_new_messages(
        self,
        session_id: str,
        original_messages: list[BetaMessageParam],
        updated_messages: list[BetaMessageParam],
    ):
        """Save any new messages that were added during processing"""
        # The sampling loop modifies the messages list in place
        # Any new messages beyond the original length should be saved
        new_messages = updated_messages[len(original_messages) :]

        from app.core.message_manager import message_manager

        for message in new_messages:
            if message["role"] == "assistant":
                # Process assistant messages
                content_text = ""
                if isinstance(message["content"], list):
                    for content_block in message["content"]:
                        if (
                            isinstance(content_block, dict)
                            and content_block.get("type") == "text"
                        ):
                            content_text += content_block.get("text", "")
                elif isinstance(message["content"], str):
                    content_text = message["content"]

                if content_text:
                    await message_manager.store_assistant_message(
                        session_id=session_id, content=content_text
                    )

            elif message["role"] == "user":
                # Process user messages (usually tool results)
                if isinstance(message["content"], list):
                    for content_block in message["content"]:
                        if (
                            isinstance(content_block, dict)
                            and content_block.get("type") == "tool_result"
                        ):
                            tool_content = content_block.get("content", "")
                            if isinstance(tool_content, list):
                                # Extract text from tool result content
                                text_content = ""
                                for item in tool_content:
                                    if (
                                        isinstance(item, dict)
                                        and item.get("type") == "text"
                                    ):
                                        text_content += item.get("text", "")

                                if text_content:
                                    await message_manager.store_tool_message(
                                        session_id=session_id,
                                        tool_result=text_content,
                                        tool_use_id=content_block.get("tool_use_id"),
                                        metadata={
                                            "is_error": content_block.get(
                                                "is_error", False
                                            )
                                        },
                                    )
