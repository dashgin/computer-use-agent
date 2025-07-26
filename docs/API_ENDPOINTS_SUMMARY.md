# API Endpoints Summary

## Overview

This document provides a comprehensive overview of all available API endpoints in the Computer Use Session Backend. The API is built with FastAPI and provides both REST endpoints for synchronous operations and WebSocket endpoints for real-time communication.

## Base URL

- **Development**: `http://localhost:8000`
- **Production**: Configure via environment variables

## REST API Endpoints

### Sessions Management

#### Create Session
- **Endpoint**: `POST /api/sessions`
- **Description**: Create a new computer use agent session
- **Request Body**:
  ```json
  {
    "title": "Optional session title",
    "metadata": {}
  }
  ```
- **Response**: Session object with ID and metadata

#### Get Session
- **Endpoint**: `GET /api/sessions/{session_id}`
- **Description**: Retrieve session information
- **Response**: Session object with current status

#### List Sessions
- **Endpoint**: `GET /api/sessions`
- **Description**: List all sessions with pagination
- **Query Parameters**:
  - `page`: Page number (default: 1)
  - `page_size`: Items per page (default: 10)
  - `sort_by`: Sort field (default: created_at)
  - `sort_order`: asc/desc (default: desc)

#### Delete Session
- **Endpoint**: `DELETE /api/sessions/{session_id}`
- **Description**: Terminate and clean up a session

### Messages

#### Send Message
- **Endpoint**: `POST /api/sessions/{session_id}/messages`
- **Description**: Send a message to an active session
- **Request Body**:
  ```json
  {
    "content": "Your message content"
  }
  ```
- **Response**: 202 Accepted with processing acknowledgment

#### Get Chat History
- **Endpoint**: `GET /api/sessions/{session_id}/messages`
- **Description**: Retrieve conversation history
- **Query Parameters**:
  - `page`: Page number
  - `page_size`: Messages per page

#### Get Latest Messages
- **Endpoint**: `GET /api/sessions/{session_id}/messages/latest`
- **Description**: Get most recent messages
- **Query Parameters**:
  - `limit`: Number of messages (max: 50)

#### Get Message Count
- **Endpoint**: `GET /api/sessions/{session_id}/messages/count`
- **Description**: Get total message count by role

### VNC Integration

#### Get VNC Connection
- **Endpoint**: `GET /api/vnc/connection`
- **Description**: Get VNC server connection details
- **Response**: Host, port, and authentication info

#### VNC Status
- **Endpoint**: `GET /api/vnc/status`
- **Description**: Check VNC server status and health

## Enhanced Message Features (Task 10)

### Advanced Message Retrieval

#### Get Specific Message
- **Endpoint**: `GET /api/sessions/{session_id}/messages/{message_id}`
- **Description**: Retrieve a specific message by ID
- **Response**: Complete message object with metadata

#### Get Filtered Messages by Role
- **Endpoint**: `GET /api/sessions/{session_id}/messages/filtered`
- **Description**: Retrieve messages filtered by role with pagination
- **Query Parameters**:
  - `role`: Message role filter (user, assistant, tool)
  - `page`: Page number
  - `page_size`: Messages per page

#### Enhanced Message Count by Role
- **Endpoint**: `GET /api/sessions/{session_id}/messages/count`
- **Description**: Get detailed message count statistics by role
- **Response**:
  ```json
  {
    "session_id": "session-id",
    "total_messages": 42,
    "by_role": {
      "user": 15,
      "assistant": 20,
      "tool": 7
    }
  }
  ```

### Tool Execution Management

#### Get Tool Executions
- **Endpoint**: `GET /api/sessions/{session_id}/tool-executions`
- **Description**: Retrieve tool executions with pagination and filtering
- **Query Parameters**:
  - `page`: Page number (default: 1)
  - `page_size`: Executions per page (default: 20, max: 100)
  - `status_filter`: Filter by execution status (pending, running, completed, failed)
- **Response**:
  ```json
  {
    "tool_executions": [...],
    "total": 25,
    "page": 1,
    "page_size": 20,
    "has_next": true,
    "status_filter": "completed"
  }
  ```

### Enhanced Pagination

All message endpoints now support advanced pagination with:
- **Efficient database queries** with proper OFFSET/LIMIT
- **Total count tracking** for accurate pagination
- **Role-based filtering** for targeted message retrieval
- **Consistent response format** across all endpoints

### Message Storage Features

#### Comprehensive Message Types
- **User Messages**: Text input from users
- **Assistant Messages**: AI responses (text, tool_use)
- **Tool Messages**: Tool execution results
- **Metadata Support**: Custom metadata for all message types

#### Tool Execution Tracking
- **Complete lifecycle tracking**: pending → running → completed/failed
- **Input/output persistence**: Full tool parameter and result storage
- **Error handling**: Detailed error messages and status tracking
- **Timeline tracking**: Start and completion timestamps

#### Data Consistency
- **Transaction management**: Atomic operations for data integrity
- **Foreign key constraints**: Proper relational data structure
- **Cascade deletion**: Automatic cleanup of related records
- **Error recovery**: Robust rollback mechanisms

## Technical Implementation

### MessageManager Class

The new `MessageManager` provides centralized message operations:

```python
# Store different message types
await message_manager.store_user_message(session_id, content, metadata)
await message_manager.store_assistant_message(session_id, content, content_type, tool_use_id)
await message_manager.store_tool_message(session_id, tool_result, tool_use_id)

# Enhanced retrieval with pagination and filtering  
response = await message_manager.get_chat_history(
    session_id=session_id,
    pagination=PaginationParams(page=1, page_size=50),
    role_filter=MessageRole.ASSISTANT,
    include_tool_executions=True
)

# Tool execution management
execution = await message_manager.store_tool_execution(
    session_id, message_id, tool_name, tool_input, tool_output, status
)
await message_manager.update_tool_execution(execution_id, tool_output, status)
```

### Database Schema Enhancements

Enhanced database models support:
- **Message role and content type** validation
- **Tool execution lifecycle** tracking
- **Metadata storage** in JSON fields
- **Proper indexing** for efficient queries
- **Foreign key relationships** for data integrity

### Performance Optimizations

- **Efficient pagination** with database-level OFFSET/LIMIT
- **Selective loading** with SQLAlchemy relationships
- **Count queries** optimized for role-based statistics
- **Connection pooling** for concurrent request handling

### System

#### Health Check
- **Endpoint**: `GET /health`
- **Description**: Comprehensive system health check
- **Response**: Status of all components (database, VNC, websocket)

#### Root
- **Endpoint**: `GET /`
- **Description**: API information and status

## WebSocket Endpoints

### Real-time Session Communication

#### WebSocket Connection
- **Endpoint**: `WS /ws/{session_id}`
- **Description**: Establish real-time communication with a session
- **Features**:
  - Session validation and authentication
  - Real-time agent message processing  
  - Progress updates streaming
  - Error handling and recovery
  - Auto-reconnection support

#### Connection Requirements
- **Session ID**: Must be a valid, active session
- **Authentication**: Optional API key via `x-api-key` header (when `REQUIRE_API_KEY=true`)
- **Validation**: Session must exist and be in 'active' status

#### Supported Message Types

##### Client → Server Messages

**Chat Message**
```json
{
  "type": "chat_message",
  "content": "Your message to the agent"
}
```

**Get Status**
```json
{
  "type": "get_status"
}
```

**Get History**
```json
{
  "type": "get_history",
  "limit": 20
}
```

**Ping**
```json
{
  "type": "ping"
}
```

##### Server → Client Messages

**Connection Established**
```json
{
  "type": "connection_established",
  "payload": {
    "connection_id": "unique-connection-id",
    "session_id": "session-id",
    "server_time": "2024-01-01T12:00:00Z"
  }
}
```

**Progress Update**
```json
{
  "type": "progress_update", 
  "payload": {
    "type": "message|tool_start|tool_complete|session_status|error",
    "data": {
      "role": "user|assistant|system",
      "content": "Message content",
      "metadata": {}
    },
    "session_id": "session-id",
    "timestamp": "2024-01-01T12:00:00Z"
  }
}
```

**Tool Execution Updates**
```json
{
  "type": "progress_update",
  "payload": {
    "type": "tool_start",
    "data": {
      "tool_name": "bash|computer|edit",
      "tool_input": {},
      "tool_use_id": "unique-id"
    }
  }
}
```

```json
{
  "type": "progress_update", 
  "payload": {
    "type": "tool_complete",
    "data": {
      "tool_name": "bash",
      "tool_output": {"result": "Command output"},
      "tool_use_id": "unique-id",
      "success": true
    }
  }
}
```

**Error Messages**
```json
{
  "type": "error",
  "payload": {
    "error_message": "Description of error",
    "error_code": "ERROR_CODE",
    "context": {}
  }
}
```

**Pong Response**
```json
{
  "type": "pong",
  "payload": {
    "server_time": "2024-01-01T12:00:00Z"
  }
}
```

**History Response**
```json
{
  "type": "history_response",
  "payload": {
    "messages": [...],
    "total_count": 25
  }
}
```

#### WebSocket Error Codes

- **4001**: Authentication required
- **4003**: Session not active
- **4004**: Session not found
- **1000**: Normal closure
- **1011**: Server error

#### Connection Management Features

- **Auto-reconnection**: Configurable automatic reconnection with exponential backoff
- **Session validation**: Validates session exists and is active before accepting connection
- **Authentication**: Optional API key authentication
- **Health monitoring**: Automatic ping/pong for connection health
- **Error recovery**: Graceful error handling with detailed error messages
- **Connection statistics**: Real-time connection metrics and statistics

### WebSocket Statistics

#### Get Connection Stats
- **Endpoint**: `GET /ws/stats`
- **Description**: Get current WebSocket connection statistics
- **Response**:
  ```json
  {
    "total_connections": 5,
    "active_sessions": 3
  }
  ```

## Authentication

### API Key Authentication (Optional)

Set `REQUIRE_API_KEY=true` in environment to enable authentication:

- **REST endpoints**: Include `X-API-Key` header
- **WebSocket**: Include `x-api-key` header (Note: Limited browser support)

### Environment Variables

```bash
# Authentication
REQUIRE_API_KEY=false
ANTHROPIC_API_KEY=your-api-key

# Model Configuration  
DEFAULT_MODEL=claude-3-5-sonnet-20241022

# Database
DATABASE_URL=sqlite:///./sessions.db

# VNC Configuration
VNC_HOST=localhost
VNC_PORT=5900
VNC_PASSWORD=optional-password

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080

# Session Management
MAX_SESSIONS=10
SESSION_TIMEOUT_MINUTES=60

# Logging
LOG_LEVEL=INFO
DEBUG=false
```

## Testing

### WebSocket Test Client

A comprehensive WebSocket test client is available at `/websocket_test_client.html` with features:

- **Connection Management**: Connect/disconnect with session validation
- **Authentication**: Optional API key input
- **Auto-reconnection**: Configurable automatic reconnection
- **Message Testing**: Send chat messages, get status, retrieve history
- **Progress Monitoring**: Real-time display of agent progress and tool execution
- **Connection Statistics**: Live connection metrics and latency monitoring
- **Error Handling**: Detailed error display and recovery guidance

### Example Usage

1. **Start a session** via REST API: `POST /api/sessions`
2. **Connect WebSocket** using session ID: `WS /ws/{session_id}`
3. **Send messages** and receive real-time agent responses
4. **Monitor progress** as agent executes tools and processes requests
5. **Handle errors** gracefully with automatic reconnection

## Rate Limiting & Performance

- **WebSocket connections**: Limited by session (multiple connections per session supported)
- **Message processing**: Queued and processed sequentially per session
- **Reconnection**: Exponential backoff with configurable limits
- **Cleanup**: Automatic cleanup of stale connections and sessions

## Error Handling

### HTTP Status Codes

- **200**: Success
- **201**: Created
- **202**: Accepted (async processing)
- **400**: Bad Request
- **401**: Unauthorized  
- **404**: Not Found
- **422**: Validation Error
- **500**: Internal Server Error

### Error Response Format

```json
{
  "error_code": "ERROR_CODE",
  "message": "Human readable error message",
  "details": {},
  "timestamp": "2024-01-01T12:00:00Z",
  "request_id": "unique-request-id"
}
```

