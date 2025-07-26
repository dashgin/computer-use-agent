"""
Database connection and session management.

This module provides database connection setup, session management,
and utilities for working with the SQLAlchemy models.
"""

import os
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.database import Base


class DatabaseManager:
    """
    Manages database connections and sessions for the application.

    Provides async database session management with proper connection pooling
    and transaction handling.
    """

    def __init__(self, database_url: str | None = None):
        """
        Initialize the database manager.

        Args:
            database_url: Database connection URL. If None, uses environment variable
                         or defaults to SQLite in-memory database.
        """
        if database_url is None:
            database_url = os.getenv("DATABASE_URL")

        self.engine = create_async_engine(database_url)
        self.async_session_maker = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def create_tables(self):
        """
        Create all database tables.

        This method creates all tables defined in the Base metadata.
        Should be called during application startup.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self):
        """
        Drop all database tables.

        This method drops all tables defined in the Base metadata.
        Useful for testing and development.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session.

        This is an async context manager that provides a database session
        with proper transaction handling and cleanup.

        Yields:
            AsyncSession: Database session for performing operations
        """
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self):
        """
        Close the database engine and all connections.

        Should be called during application shutdown.
        """
        await self.engine.dispose()


# Global database manager instance
db_manager = DatabaseManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function for FastAPI to get database sessions.

    This function can be used as a FastAPI dependency to inject
    database sessions into route handlers.

    Yields:
        AsyncSession: Database session for the request
    """
    async for session in db_manager.get_session():
        yield session
        break


async def test_db_connection() -> bool:
    """
    Test database connection health.

    Returns:
        bool: True if database connection is healthy, False otherwise
    """
    try:
        async for session in db_manager.get_session():
            # Execute a simple query to test connection
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception:
        return False
