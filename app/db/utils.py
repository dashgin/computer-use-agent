"""
Database utility functions for common operations.
"""

from typing import Optional

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.connection import DatabaseManager

logger = get_logger(__name__)


async def initialize_database(database_url: Optional[str] = None) -> None:
    """
    Initialize the database by creating all tables.

    Args:
        database_url: Optional database URL. If None, uses default from environment.
    """
    db_manager = DatabaseManager(database_url)
    await db_manager.create_tables()
    await db_manager.close()
    logger.info("✅ Database initialized successfully!")


async def reset_database(database_url: Optional[str] = None) -> None:
    """
    Reset the database by dropping and recreating all tables.

    Args:
        database_url: Optional database URL. If None, uses default from environment.
    """
    db_manager = DatabaseManager(database_url)
    await db_manager.drop_tables()
    await db_manager.create_tables()
    await db_manager.close()
    logger.info("✅ Database reset successfully!")


async def check_database_health(database_url: Optional[str] = None) -> bool:
    """
    Check if the database is accessible and has the expected schema.

    Args:
        database_url: Optional database URL. If None, uses default from environment.

    Returns:
        bool: True if database is healthy, False otherwise.
    """
    try:
        db_manager = DatabaseManager(database_url)

        async for session in db_manager.get_session():
            # Try to query each table to ensure they exist
            await session.execute(text("SELECT COUNT(*) FROM sessions"))
            await session.execute(text("SELECT COUNT(*) FROM messages"))
            await session.execute(text("SELECT COUNT(*) FROM tool_executions"))
            break

        await db_manager.close()
        return True
    except Exception as e:
        logger.error(f"❌ Database health check failed: {e}")
        return False


if __name__ == "__main__":
    import asyncio
    import sys

    async def main():
        if len(sys.argv) < 2:
            logger.error("Usage: python -m app.db.utils <command>")
            logger.error("Commands: init, reset, health")
            return

        command = sys.argv[1]

        if command == "init":
            await initialize_database()
        elif command == "reset":
            await reset_database()
        elif command == "health":
            is_healthy = await check_database_health()
            if is_healthy:
                logger.info("✅ Database is healthy!")
            else:
                logger.error("❌ Database health check failed!")
                sys.exit(1)
        else:
            logger.error(f"Unknown command: {command}")
            sys.exit(1)

    asyncio.run(main())
