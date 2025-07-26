# Database Setup and Management

This directory contains the database models, connection management, and utilities for the computer use session backend.

## Overview

The database system uses:
- **SQLAlchemy 2.0** with async support for ORM operations
- **Alembic** for database migrations
- **SQLite** with aiosqlite for async operations
- **Pydantic** models for API validation (defined separately)

## Database Schema

The system uses three main tables:

### Sessions Table
- `id` (String, Primary Key): Unique session identifier
- `created_at` (DateTime): Session creation timestamp
- `updated_at` (DateTime): Last update timestamp
- `status` (String): Session status (active, completed, failed, etc.)
- `title` (String, Optional): Human-readable session title
- `session_metadata` (JSON): Additional session metadata

### Messages Table
- `id` (Integer, Primary Key): Auto-incrementing message ID
- `session_id` (String, Foreign Key): Reference to sessions table
- `role` (String): Message role (user, assistant, tool)
- `content` (Text): Message content
- `content_type` (String): Content type (text, tool_use, tool_result)
- `tool_use_id` (String, Optional): Tool use identifier for tool messages
- `timestamp` (DateTime): Message timestamp
- `message_metadata` (JSON): Additional message metadata

### Tool Executions Table
- `id` (String, Primary Key): Unique tool execution identifier
- `session_id` (String, Foreign Key): Reference to sessions table
- `message_id` (Integer, Foreign Key): Reference to messages table
- `tool_name` (String): Name of the executed tool
- `tool_input` (JSON): Tool input parameters
- `tool_output` (JSON, Optional): Tool execution results
- `status` (String): Execution status (pending, running, completed, failed)
- `started_at` (DateTime): Execution start time
- `completed_at` (DateTime, Optional): Execution completion time
- `error_message` (Text, Optional): Error message if execution failed

## Usage

### Database Connection

```python
from app.db.connection import DatabaseManager, get_db_session

# Initialize database manager
db_manager = DatabaseManager()

# Get a database session (for use in FastAPI dependencies)
async def my_endpoint(db: AsyncSession = Depends(get_db_session)):
    # Use db session here
    pass

# Manual session management
async for session in db_manager.get_session():
    # Use session here
    break
```

### Working with Models

```python
from app.models.database import Session, Message, ToolExecution
from sqlalchemy import select

# Create a new session
new_session = Session(
    id="session-123",
    title="My Session",
    status="active",
    session_metadata={"key": "value"}
)
db.add(new_session)
await db.commit()

# Query sessions
result = await db.execute(select(Session).where(Session.status == "active"))
active_sessions = result.scalars().all()

# Create a message
message = Message(
    session_id="session-123",
    role="user",
    content="Hello, world!",
    content_type="text"
)
db.add(message)
await db.commit()
```

## Database Management

### Migrations

The project uses Alembic for database migrations:

```bash
# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Downgrade to previous version
alembic downgrade -1

# Show current migration status
alembic current

# Show migration history
alembic history
```

### Utilities

Use the database utilities for common operations:

```bash
# Initialize database (create tables)
python -m app.db.utils init

# Reset database (drop and recreate tables)
python -m app.db.utils reset

# Check database health
python -m app.db.utils health
```

### Environment Configuration

Configure the database URL using environment variables:

```bash
# For development (default)
export DATABASE_URL="sqlite+aiosqlite:///./sessions.db"

# For testing
export DATABASE_URL="sqlite+aiosqlite:///:memory:"

# For production (example with PostgreSQL)
export DATABASE_URL="postgresql+asyncpg://user:password@localhost/dbname"
```

## Development Setup

1. Ensure all dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```

2. Run initial migration to create tables:
   ```bash
   alembic upgrade head
   ```

3. Verify database health:
   ```bash
   python -m app.db.utils health
   ```

4. Run the test script to verify everything works:
   ```bash
   python test_database.py
   ```

## Production Considerations

- **Connection Pooling**: The DatabaseManager automatically configures appropriate connection pooling
- **Migrations**: Always run `alembic upgrade head` during deployment
- **Backup**: Implement regular database backups for production
- **Monitoring**: Use the health check utility for monitoring
- **Security**: Use environment variables for database credentials
- **Performance**: Consider adding database indexes for frequently queried columns

## Troubleshooting

### Common Issues

1. **Migration Errors**: Ensure the database URL in `alembic.ini` matches your environment
2. **Connection Issues**: Check that the database file is writable and the directory exists
3. **Schema Mismatches**: Run `alembic upgrade head` to apply pending migrations
4. **Async Context Issues**: Use `async for session in db_manager.get_session():` for manual session management

### Debugging

Enable SQL logging by setting the environment variable:
```bash
export DATABASE_ECHO=true
```

This will print all SQL queries to the console for debugging purposes.