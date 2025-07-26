"""
Application lifecycle event handlers.
"""

from fastapi import FastAPI

from app.core.logging import get_logger
from app.core.websocket_manager import websocket_manager
from app.db.utils import initialize_database

logger = get_logger(__name__)


async def startup_event():
    """Application startup handler."""
    logger.info("Migrating database to latest version...")
    await initialize_database()
    logger.info("Database migration complete")


async def shutdown_event():
    """Application shutdown handler."""
    logger.info("Shutting down application...")
    await websocket_manager.cleanup()
    logger.info("Application shutdown complete")


def register_events(app: FastAPI):
    """Register startup and shutdown events with the FastAPI app."""
    app.add_event_handler("startup", startup_event)
    app.add_event_handler("shutdown", shutdown_event) 