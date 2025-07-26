from typing import Annotated

from fastapi import Depends

from app.core.message_manager import MessageManager
from app.core.session_manager import SessionManager


def get_message_manager() -> MessageManager:
    return MessageManager()


MessageManagerDep = Annotated[MessageManager, Depends(get_message_manager)]


def get_session_manager() -> SessionManager:
    return SessionManager()


SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
