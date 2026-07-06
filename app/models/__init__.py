"""Import all models here so Alembic's autogenerate + Base.metadata see them."""
from app.models.ai_event import AIEvent
from app.models.ticket import Ticket
from app.models.user import User

__all__ = ["User", "Ticket", "AIEvent"]
