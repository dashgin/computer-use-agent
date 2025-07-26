"""
FastAPI main application module.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import health, messages, sessions, vnc, websocket
from app.core.config import settings
from app.core.events import register_events
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger

# Configure logging
configure_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="Computer Use Session Backend",
    description="Backend API for managing computer use agent sessions with real-time communication, VNC integration, and persistent storage",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exception handlers
register_exception_handlers(app)

# Register event handlers
register_events(app)

# Include API routers
app.include_router(sessions.router)
app.include_router(messages.router)
app.include_router(vnc.router)
app.include_router(health.router)
app.include_router(websocket.router)

logger.info("FastAPI application initialized", app_name=settings.APP_NAME)


@app.get("/")
async def root():
    """Serve the frontend application."""
    frontend_path = str(settings.BASE_DIR / "static/index.html")
    return FileResponse(frontend_path)


@app.get("/api")
async def api_root():
    """API root endpoint for health check."""
    return {
        "message": "Computer Use Session Backend API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "status": "running",
    }
